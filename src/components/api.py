import os
import requests
from dotenv import load_dotenv
from datetime import datetime
from src.logger import setup_logger

# Setup logger
logger = setup_logger()

# Load API-Key from .env file
load_dotenv()

# API Configuration
API_KEY = os.getenv('API_KEY')
BASE_URL = 'https://api.spoonacular.com/recipes'

# API limit tracking
DAILY_LIMIT = 150
api_calls = {
    'count': 0,
    'reset_time': datetime.now()
}

if not API_KEY: 
    logger.error("API_KEY environment variable is not set")
    logger.error("Please make sure you have created a .env file with your API key")
    raise ValueError("API key is required")

def check_api_limit():
    """Check if we've hit the daily API limit"""
    global api_calls
    
    # Reset counter if it's a new day
    now = datetime.now()
    if now.date() > api_calls['reset_time'].date():
        api_calls = {
            'count': 0,
            'reset_time': now
        }
    
    # Check if we've hit the limit
    if api_calls['count'] >= DAILY_LIMIT:
        return False
    
    return True

def increment_api_counter():
    """Increment the API call counter"""
    global api_calls
    api_calls['count'] += 1

def search_recipes(query, search_query, number=3):
    """
    Search recipes using Spoonacular API
    """
    try:
        # Check API limit
        if not check_api_limit():
            logger.warning("Daily API limit reached. Please try again tomorrow.")
            return {'error': 'API_LIMIT_REACHED'}
            
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
        increment_api_counter()  # Increment counter after successful API call
        results = response.json()['results']
        
        if not results and len(search_query.split()) > 1:
            for keyword in search_query.split():
                params['query'] = keyword
                logger.info(f"Trying with single keyword: {keyword}")
                response = requests.get(f'{BASE_URL}/complexSearch', params=params)
                response.raise_for_status()
                results = response.json()['results']
                if results:
                    break
        
        if not results:
            logger.info("No results found")
            return []
            
        logger.info(f"Found {len(results)} recipes")
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
            
        return recipes
        
    except requests.RequestException as e:
        logger.error(f"API Error: {str(e)}")
        return []