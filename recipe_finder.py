import os
import json
import string
import threading
from flask import Flask, request, jsonify, render_template
from nltk.corpus import stopwords
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from collections import defaultdict
import time

app = Flask(__name__)

current_dir = os.path.dirname(os.path.abspath(__file__))
json_path = os.path.join(current_dir, 'recipes.json')

# Read the file
try:
    with open(json_path, 'r', encoding="utf-8") as file:
        recipes_data = json.load(file)
except FileNotFoundError:
    print(f"Error: The file {json_path} was not found.")
    recipes_data = []
except json.JSONDecodeError:
    print(f"Error: The file {json_path} is not a valid JSON file.")
    recipes_data = []

#load stop.words
stop_words = set(stopwords.words('english'))

def clean_text(text):
    #remove punctuation
    text = text.translate(str.maketrans('','', string.punctuation))

    #remove stop words
    words = text.split()
    cleaned_words = [word for word in words if word.lower() not in stop_words]
    return ' '.join(cleaned_words)

# prep recipes texts
recipe_texts = [clean_text(" ".join(recipe['ingredients'])) for recipe in recipes_data]

exit_commands = [
    "exit", 
    "quit", 
    "bye", 
    "goodbye", 
    "see you later", 
    "leave", 
    "end chat", 
    "stop", 
    "close", 
    "finish"]

# TF-IDF vectorizer
vectorizer = TfidfVectorizer()
X = vectorizer.fit_transform(recipe_texts)

def search_recipes(query, vectorizer, X, recipes_data, top_n=3):
    query_cleaned = clean_text(query)
    query_vec = vectorizer.transform([query_cleaned])
    similarities = cosine_similarity(query_vec, X).flatten()
    top_indices = similarities.argsort()[-top_n:][::-1]
    return [recipes_data[i] for i in top_indices if similarities[i] > 0]

# Add this after app initialization
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
    results = search_recipes(query, vectorizer, X, recipes_data)

    return jsonify({
        'rate_limited': False,
        'results': [{
            'name': recipe['name'],
            'ingredients': ', '.join(recipe['ingredients']),
            'steps': recipe['steps']
        } for recipe in results]
    })

def chat():

    welcome_message = """
    Bot: Hello and welcome to the Local Flavor Bot! 🍳👨‍🍳👩‍🍳

    I'm here to help you discover delicious recipes based on the ingredients you have or the dishes you're craving.

    How can I assist you today?
    """
    print(welcome_message)

    while True:
        query = input("You: ")
        if query.lower() in exit_commands:
            print("Bot: See you later!")
            break
        
        # Return recipes
        recipes = search_recipes(query, vectorizer, X, recipes_data)

        if recipes:
            print("Bot: Here are some recipes that might interest you with the ingredients you provided:")
            for i, recipe in enumerate(recipes,1):
                print(f"\n[{i}.{recipe['name']}")
                print(f"Ingredients: {','.join(recipe['ingredients'])}")
                print(f"Instructions: {recipe['steps']}")

        else: 
            print("Bot: I'm sorry, I couldn't find any matching recipes. Can you try rephrasing your request?")
            print() # Add a blank line for readibility

def run_flask():
    app.run(debug=False, use_reloader=False, host='0.0.0.0', port=5001)
    
def run_cli():
    chat()

if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    # Run CLI FE in main thread 
    run_cli()

    # Wait Flask thread 
    flask_thread.join()

