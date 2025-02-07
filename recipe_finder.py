import os
import string
import threading
import requests
import numpy as np
from flask import Flask, request, jsonify, render_template
from collections import defaultdict
import time
from sentence_transformers import SentenceTransformer
import torch
from dotenv import load_dotenv
import re

# Load API-Key from .env file
load_dotenv()

app = Flask(__name__) 

#  API Configuration
API_KEY = os.getenv('API_KEY')
BASE_URL = 'https://api.spoonacular.com/recipes'

if not API_KEY: 
    print("Error: API_KEY environment variable is not set")
    print("Please make sure you have created a .env file with your API key")
    raise ValueError("API key is required")

# Initialize the transformer model 
print("Loading Transformer model...") 
model = SentenceTransformer('all-MiniLM-L6-v2') 
cached_recipes = [] 
recipe_embeddings = None 

def preprocess_query(query):
    """Extract relevant search terms from natural language query"""
    # Common words to remove, organized by category
    cooking_stopwords = {
        # Cooking related
        'recipe', 'cook', 'cooking', 'make', 'making', 'prepare', 'preparing',
        'meal', 'food', 'eat', 'eating',
        
        # Action words
        'want', 'need', 'show', 'tell', 'give', 'find', 'search', 'looking',
        'using', 'have', 'has', 'had', 'help', 'recommend',
        
        # Common words
        'something', 'anything', 'with', 'without', 'can', 'could', 'should',
        'would', 'like', 'please', 'bit', 'lately', 'tbh',
        
        # Pronouns and articles
        'i', 'me', 'my', 'am', 'im', 'a', 'an', 'the'
    }
    
    # Important food and health related words to keep
    important_words = {
        # Meal types
        'soup', 'stew', 'salad', 'breakfast', 'lunch', 'dinner', 'dessert',
        
        # Diet preferences
        'healthy', 'vegetarian', 'vegan', 'gluten-free', 'dairy-free',
        
        # Health conditions
        'sick', 'cold', 'flu', 'energy', 'power', 'boost', 'immune',
        'healing', 'recovery', 'health', 'wellness'
    }
    
    # Remove punctuation
    query = query.lower()
    query = re.sub(r'[^\w\s-]', ' ', query)  
    
    # Split into words
    words = query.split()
    
    # Keep important words and words not in stopwords
    filtered_words = [word for word in words if word in important_words or word not in cooking_stopwords]
    
    # If no important words found, return original query
    if not filtered_words:
        return query
        
    # Add 'healthy' if health-related words are present
    health_indicators = {'sick', 'cold', 'flu', 'energy', 'power', 'immune', 'healing', 'recovery'}
    if any(word in health_indicators for word in filtered_words):
        filtered_words.append('healthy')
    
    return ' '.join(filtered_words)

def cache_recipes(recipes):
    """Cache recipe embeddings for faster subsequent searches"""
    global cached_recipes, recipe_embeddings
    
    if not recipes:
        return
        
    # Store recipes
    cached_recipes = recipes
    
    # Create recipe texts for embedding
    recipe_texts = [
        f"{recipe['name']} {' '.join(recipe['ingredients'])}"
        for recipe in recipes
    ]
    
    # Generate embeddings
    recipe_embeddings = model.encode(recipe_texts, convert_to_tensor=True)

def semantic_search(query, recipes, top_k=4):
    """Search recipes using transformer embeddings"""
    if not recipes or recipe_embeddings is None:
        return []

    # Generate query embedding
    query_embedding = model.encode(query, convert_to_tensor=True)
    
    # Calculate cosine similarities
    cos_scores = torch.nn.functional.cosine_similarity(query_embedding.unsqueeze(0), recipe_embeddings)
    
    # Get top-k recipes
    top_results = torch.topk(cos_scores, k=min(top_k, len(recipes)))
    
    return [recipes[idx] for idx in top_results.indices]

def is_food_related(word, threshold=0.4):
    """Check if a word is food-related using semantic similarity"""
    # Common food categories to compare against
    food_categories = [
        "food", "ingredient", "vegetable", "fruit", "meat", "spice", 
        "herb", "grain", "dairy", "seafood", "dish", "meal"
    ]
    
    # Encode the word and categories
    word_embedding = model.encode(word, convert_to_tensor=True)
    category_embeddings = model.encode(food_categories, convert_to_tensor=True)
    
    # Calculate similarities
    similarities = torch.nn.functional.cosine_similarity(
        word_embedding.unsqueeze(0), category_embeddings
    )
    
    # Return True if the word is similar enough to any food category
    return torch.max(similarities).item() > threshold

def extract_excluded_ingredients(query):
    """Extract ingredients that should be excluded from the recipe"""
    # Negative patterns to check
    negative_patterns = [
        'no', 'not', 'without', 'exclude', "don't", 'doesnt', 'doesn\'t',
        'except', 'excluding', 'free', '-free', 'none', 'cant', "can't",
        'cannot', 'avoid', 'allergic', 'allergy', 'intolerant', 'intolerance'
    ]
    
    # Health condition patterns that indicate exclusion
    health_patterns = [
        "can't eat", "cannot eat", "cant eat",
        "can't have", "cannot have", "cant have",
        "allergic to", "intolerant to",
        "avoid eating", "avoid having",
        "sensitive to", "bad with"
    ]
    
    excluded = set()
    words = query.lower().split()

    # Check for health condition patterns
    query_lower = query.lower()
    for pattern in health_patterns:
        if pattern in query_lower:
            # Find the word after the pattern
            pattern_index = query_lower.find(pattern) + len(pattern)
            remaining_text = query_lower[pattern_index:].strip()
            next_word = remaining_text.split()[0] if remaining_text else ''
            if next_word and is_food_related(next_word):
                excluded.add(next_word)
    
    # Check for patterns like "dairy-free" or "gluten-free"
    for word in words:
        if word.endswith('-free'):
            base = word.replace('-free', '')
            if base in ['dairy', 'gluten', 'nut', 'egg', 'soy', 'lactose']:
                excluded.add(base)
    
    # Check for negative patterns
    for i, word in enumerate(words):
        if word in negative_patterns and i + 1 < len(words):
            next_word = words[i + 1]
            if is_food_related(next_word):
                excluded.add(next_word)

    # Common allergens and their variations
    allergen_mapping = {
        'milk': ['milk', 'dairy', 'lactose', 'cream', 'cheese', 'butter', 'yogurt', 'whey'],
        'egg': ['egg', 'eggs'],
        'nuts': ['nuts', 'peanuts', 'almonds', 'cashews', 'walnuts'],
        'soy': ['soy', 'soybeans', 'tofu', 'soya'],
        'gluten': ['gluten', 'wheat', 'rye', 'barley']
    }
    
    # Expand excluded ingredients with their variations
    expanded_excluded = set()
    for item in excluded:
        for allergen, variations in allergen_mapping.items():
            if item in variations or item == allergen:
                expanded_excluded.add(allergen)
                expanded_excluded.update(variations)
                break
        if item not in expanded_excluded:
            expanded_excluded.add(item)
    
    print(f"Found excluded ingredients: {expanded_excluded}")  # Debug print
    return list(expanded_excluded)

def search_recipes(query, number=3):
    """
    Search recipes using Spoonacular API and enhance results with transformer-based search
    """
    try:
        query = query.lower().strip()
        
        keywords = []
        
        health_terms = {
            'energy', 'healthy', 'nutritious', 'protein',
            'vitamin', 'minerals', 'boost', 'power'
        }
        
        common_words = {
            'i', 'me', 'my', 'can', 'you', 'please', 'want', 'would', 'like', 'need',
            'help', 'looking', 'for', 'some', 'recipe', 'recipes', 'with', 'using',
            'make', 'cook', 'cooking', 'recommend', 'show', 'tell', 'give', 'a', 'an',
            'the', 'and', 'or', 'but', 'to', 'that', 'this', 'these', 'those', 'fill'
        }
        
        words = query.split()
        
        for word in words:
            if len(word) > 2 and word not in common_words:
                if is_food_related(word):
                    keywords.append(word)
                    print(f"Found food-related word: {word}")
                
        has_health_terms = any(term in query for term in health_terms)
        if has_health_terms:
            keywords.append('healthy')
            
        if not keywords:
            search_query = query
        else:
            search_query = ' '.join(keywords)
            
        print(f"Original query: {query}")
        print(f"Keywords found: {keywords}")
        print(f"Search query: {search_query}")
        
        
        params = {
            'apiKey': API_KEY,
            'query': search_query,
            'number': number * 2,
            'addRecipeInformation': True,
            'fillIngredients': True,
            'instructionsRequired': True
        }
        
        response = requests.get(f'{BASE_URL}/complexSearch', params=params)
        response.raise_for_status()
        results = response.json()['results']
        
        if not results and len(keywords) > 1:
            for keyword in keywords:
                params['query'] = keyword
                print(f"Trying with single keyword: {keyword}")
                response = requests.get(f'{BASE_URL}/complexSearch', params=params)
                response.raise_for_status()
                results = response.json()['results']
                if results:
                    break
        
        if not results:
            print("No results found")
            return []
            
        print(f"Found {len(results)} recipes")
        recipes = []
        for recipe in results:
            recipes.append({
                'name': recipe['title'],
                'ingredients': [ingredient['original'] for ingredient in recipe.get('extendedIngredients', [])],
                'steps': [step['step'] for step in recipe.get('analyzedInstructions', [{}])[0].get('steps', [])]
                        if recipe.get('analyzedInstructions') else recipe.get('instructions', '').split('\n'),
                'readyInMinutes': recipe.get('readyInMinutes', 0),
                'servings': recipe.get('servings', 0),
                'sourceUrl': recipe.get('sourceUrl', '')
            })
        
        cache_recipes(recipes)
        
        # most relevant results with semantic search
        return semantic_search(query, recipes, number)
        
    except requests.RequestException as e:
        print(f"API Error: {str(e)}")
        if cached_recipes:
            return semantic_search(query, cached_recipes, number)
        return []

request_counts = defaultdict(list)

def is_rate_limited(ip):
    now = time.time()
    # Remove requests older than 5 seconds
    request_counts[ip] = [req_time for req_time in request_counts[ip] if now - req_time < 5]
    # Add current request
    request_counts[ip].append(now)
    # Check if more than 5 requests in last 5 seconds
    return len(request_counts[ip]) > 5

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    ip = request.remote_addr
    if is_rate_limited(ip):
        return jsonify({
            'error': 'Rate limit exceeded. Please wait a few seconds before trying again.',
            'rate_limited': True
        }), 429

    query = request.form['query']
    results = search_recipes(query)

    return jsonify({
        'rate_limited': False,
        'results': [{
            'name': recipe['name'],
            'ingredients': ', '.join(recipe['ingredients']),
            'steps': recipe['steps'],
            'readyInMinutes': recipe['readyInMinutes'],
            'servings': recipe['servings'],
            'sourceUrl': recipe['sourceUrl']
        } for recipe in results]
    })

def chat():
    welcome_message = """
    Hello! I'm Local Flavor Bot! 🍳👨‍🍳👩‍🍳

    I'm your personal culinary assistant, ready to help you discover delicious recipes based on your ingredients or cravings.

    How can I assist you today?
    """
    print(welcome_message)

    exit_commands = [
        "exit", "quit", "bye", "goodbye", "see you later",
        "leave", "end chat", "stop", "close", "finish"
    ]

    while True:
        query = input("You: ")
        if query.lower() in exit_commands:
            print("Bot: See you later!")
            break
        
        recipes = search_recipes(query)

        if recipes:
            print("\nBot: Here are some recipes that might interest you:")
            for i, recipe in enumerate(recipes, 1):
                print("\n" + "=" * 80)
                print(f"\n📝 Recipe #{i}: {recipe['name']}")
                print("=" * 80)
                
                print(f"\n⏲️  Preparation Details:")
                print(f"   • Ready in: {recipe['readyInMinutes']} minutes")
                print(f"   • Servings: {recipe['servings']}")
                
                print(f"\n🧂 Ingredients:")
                for ingredient in recipe['ingredients']:
                    print(f"   • {ingredient}")
                
                print("\n📋 Instructions:")
                if isinstance(recipe['steps'], list):
                    for step_num, step in enumerate(recipe['steps'], 1):
                        if isinstance(step, dict) and 'step' in step:
                            print(f"   {step_num}. {step['step']}")
                        elif isinstance(step, str):
                            print(f"   {step_num}. {step}")
                else:
                    print(f"   {recipe['steps']}")
                
                print(f"\n🔗 Source URL: {recipe['sourceUrl']}")
                print("\n" + "=" * 80)
        else:
            print("\nBot: I'm sorry, I couldn't find any matching recipes. Can you try rephrasing your request?")

def run_flask():
    app.run(debug=False, use_reloader=False, host='0.0.0.0', port=5001)
    
def run_cli():
    chat()

if __name__ == '__main__':
    import sys
    
    # Check if --web flag is provided
    if len(sys.argv) > 1 and sys.argv[1] == '--web':
        # Run both web and CLI
        flask_thread = threading.Thread(target=run_flask)
        flask_thread.start()
        run_cli()
        flask_thread.join()
    else:
        # Run only CLI by default
        run_cli()