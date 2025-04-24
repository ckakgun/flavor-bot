import sys
import time
import os
from collections import defaultdict
from flask import Flask, request, jsonify, render_template
import torch
import torch.nn.functional as F
from sentence_transformers import SentenceTransformer
from src.components.api import search_recipes
from src.logger import setup_logger

# Setup logger
logger = setup_logger()

# Initialize Flask app
app = Flask(__name__)

# Initialize the transformer model 
logger.info("Loading Transformer model...") 
model = SentenceTransformer('all-MiniLM-L6-v2') 
cached_recipes = [] 
recipe_embeddings = None 

# Rate limiting
request_counts = defaultdict(list)

def is_rate_limited(ip):
    """Check if the IP is rate limited"""
    now = time.time()
    # Remove requests older than 5 seconds
    request_counts[ip] = [req_time for req_time in request_counts[ip] if now - req_time < 5]
    # Add current request
    request_counts[ip].append(now)
    # Check if more than 5 requests in last 5 seconds
    return len(request_counts[ip]) > 5

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
    # Normalize the embeddings
    query_embedding = query_embedding / query_embedding.norm(dim=0, keepdim=True)
    normalized_recipe_embeddings = recipe_embeddings / recipe_embeddings.norm(dim=1, keepdim=True)
    
    # Calculate dot product (cosine similarity with normalized vectors)
    cos_scores = torch.matmul(query_embedding, normalized_recipe_embeddings.T)
    
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
    
    # Normalize embeddings
    word_embedding = word_embedding / word_embedding.norm()
    category_embeddings = category_embeddings / category_embeddings.norm(dim=1, keepdim=True)
    
    # Calculate similarities using dot product of normalized vectors (cosine similarity)
    similarities = torch.matmul(word_embedding, category_embeddings.T)
    
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
    
    logger.debug(f"Found excluded ingredients: {expanded_excluded}")
    return list(expanded_excluded)

def process_query(query, number=3):
    """
    Process user query and enhance with semantic search
    """
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
                logger.debug(f"Found food-related word: {word}")
                
    has_health_terms = any(term in query for term in health_terms)
    if has_health_terms:
        keywords.append('healthy')
            
    if not keywords:
        search_query = query
    else:
        search_query = ' '.join(keywords)
            
    logger.info(f"Original query: {query}")
    logger.debug(f"Keywords found: {keywords}")
    logger.debug(f"Search query: {search_query}")
    
    # Call API to get recipes
    recipes = search_recipes(query, search_query, number)
    
    if isinstance(recipes, dict) and recipes.get('error') == 'API_LIMIT_REACHED':
        return recipes
        
    # Cache recipes for semantic search
    if recipes:
        cache_recipes(recipes)
        # Return most relevant results with semantic search
        return semantic_search(query, recipes, number)
    
    # Try with cached recipes if available
    if cached_recipes:
        return semantic_search(query, cached_recipes, number)
        
    return []

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
    results = process_query(query)

    # Check API limit
    if isinstance(results, dict) and results.get('error') == 'API_LIMIT_REACHED':
        return jsonify({
            'error': 'Daily API limit reached. Please try again tomorrow.',
            'api_limited': True
        }), 429

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
    logger.info("Starting chat session")
    print(welcome_message)

    exit_commands = [
        "exit", "quit", "bye", "goodbye", "see you later",
        "leave", "end chat", "stop", "close", "finish"
    ]

    while True:
        query = input("You: ")
        if query.lower() in exit_commands:
            logger.info("Chat session ended by user")
            print("Bot: See you later!")
            break
        
        logger.info(f"User query: {query}")
        # Process the query like we do in the web route
        results = process_query(query)

        # Check the API limit
        if isinstance(results, dict) and results.get('error') == 'API_LIMIT_REACHED':
            logger.warning("API limit reached during chat session")
            print("\nBot: I'm sorry, we've reached our daily API limit. Please try again tomorrow!")
            continue

        if results:
            logger.info(f"Found {len(results)} recipes for query: {query}")
            print("\nBot: Here are some recipes that might interest you:")
            for i, recipe in enumerate(results, 1):
                print("\n" + "=" * 20)
                print(f"📝 Recipe #{i}: {recipe['name']}")
                print("=" * 20)
            
                print(f"⏲️  Preparation Details:")
                print(f"   • Ready in: {recipe['readyInMinutes']} minutes")
                print(f"   • Servings: {recipe['servings']}")
                
                print(f"\n🧂 Ingredients:")
                for ingredient in recipe['ingredients']:
                    print(f"   • {ingredient}")
                
                print(f"\n📋 Instructions:")
                if isinstance(recipe['steps'], list):
                    for step_num, step in enumerate(recipe['steps'], 1):
                        if isinstance(step, dict) and 'step' in step:
                            print(f"   {step_num}. {step['step']}")
                        elif isinstance(step, str):
                            print(f"   {step_num}. {step}")
                else:
                    print(f"   {recipe['steps']}")
                
                print(f"\n🔗 Source URL: {recipe['sourceUrl']}")
                print("=" * 20)
        else:
            logger.warning(f"No recipes found for query: {query}")
            print("\nBot: I'm sorry, I couldn't find any matching recipes. Can you try rephrasing your request?")


def run_flask():
    """
    Run the Flask application
    """
    logger.info("Starting web interface on http://localhost:5001")
    app.run(debug=False, use_reloader=False, host='0.0.0.0', port=5001)

def run_cli():
    """
    Run the CLI interface
    """
    logger.info("Starting CLI interface")
    chat()

def run_app():
    """
    Main entry point for the application
    """
    if len(sys.argv) > 1 and sys.argv[1] == '--cli':
        logger.info("Starting CLI interface")
        run_cli()
    else:
        logger.info("Starting web interface on http://localhost:5001")
        run_flask()