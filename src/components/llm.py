import os
import json
import time
from typing import Dict, List, Optional, Any
from collections import defaultdict
from dotenv import load_dotenv
from src.logger import setup_logger

load_dotenv()

logger = setup_logger()

LLM_PROVIDER = os.getenv('LLM_PROVIDER', 'groq')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
MAX_QUERY_LENGTH = 500
MIN_QUERY_LENGTH = 2
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX_CALLS = 30

llm_request_tracker = defaultdict(list)

class GuardrailViolation(Exception):

    pass

class LLMClient:
    def __init__(self):
        """
        Initialize the LLM client
        """
        self.provider = LLM_PROVIDER
        self.client = None
        self._initialize_client()
        
    def _initialize_client(self):
        """
        Initialize the LLM client based on the provider
        """
        if self.provider == 'groq' and GROQ_API_KEY:
            try:
                from groq import Groq
                self.client = Groq(api_key=GROQ_API_KEY)
                logger.info("Initialized Groq client")
            except ImportError:
                logger.warning("Groq package not installed, falling back")
                self.provider = 'none'
            except Exception as e:
                logger.error(f"Failed to initialize Groq client: {e}")
                self.provider = 'none'
                
        elif self.provider == 'ollama':
            try:
                import ollama
                self.client = ollama
                logger.info("Initialized Ollama client")
            except ImportError:
                logger.warning("Ollama package not installed, falling back")
                self.provider = 'none'
            except Exception as e:
                logger.error(f"Failed to initialize Ollama client: {e}")
                self.provider = 'none'
        else:
            self.provider = 'none'
            logger.info("LLM provider disabled or not configured")
    
    def is_available(self) -> bool:
        """
        Check if the LLM is available
        """
        return self.provider != 'none' and self.client is not None
    
    def _call_groq(self, messages: List[Dict], temperature: float = 0.3, max_tokens: int = 500) -> str:
        """
        Call the Groq LLM
        """
        try:
            response = self.client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=0.9
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Groq API error: {e}")
            raise
    
    def _call_ollama(self, messages: List[Dict], temperature: float = 0.3) -> str:
        """
        Call the Ollama LLM
        """
        try:
            response = self.client.chat(
                model="llama3.1:8b",
                messages=messages,
                options={
                    "temperature": temperature,
                    "top_p": 0.7
                }
            )
            return response['message']['content']
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            raise
    
    def call(self, messages: List[Dict], temperature: float = 0.3, max_tokens: int = 500) -> Optional[str]:
        """
        Call the LLM
        """
        if not self.is_available():
            return None
            
        try:
            if self.provider == 'groq':
                return self._call_groq(messages, temperature, max_tokens)
            elif self.provider == 'ollama':
                return self._call_ollama(messages, temperature)
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return None
        
        return None

llm_client = LLMClient()

def validate_input(query: str, ip_address: str = None) -> None:
    """
    Validate the input of the LLM
    """
    if not query or not isinstance(query, str):
        raise GuardrailViolation("Invalid query type")
    
    query_stripped = query.strip()
    
    if len(query_stripped) < MIN_QUERY_LENGTH:
        raise GuardrailViolation("Query too short")
    
    if len(query_stripped) > MAX_QUERY_LENGTH:
        raise GuardrailViolation("Query too long")
    
    injection_patterns = [
        'ignore previous',
        'ignore all previous',
        'disregard previous',
        'forget previous',
        'new instructions',
        'system prompt',
        'you are now',
        'act as',
        'roleplay',
        'pretend you are'
    ]
    
    query_lower = query_stripped.lower()
    for pattern in injection_patterns:
        if pattern in query_lower:
            logger.warning(f"Potential injection attempt detected: {pattern}")
            raise GuardrailViolation("Invalid user query pattern detected")
    
    if not filter_content(query_stripped):
        logger.warning(f"Off-topic query detected: {query_stripped}")
        raise GuardrailViolation("Query must be food or recipe related")
    
    if ip_address:
        _check_rate_limit(ip_address)

def _check_rate_limit(ip_address: str) -> None:
    """
    Check the rate limit of the LLM calls
    """
    now = time.time()
    cutoff = now - RATE_LIMIT_WINDOW
    
    llm_request_tracker[ip_address] = [
        ts for ts in llm_request_tracker[ip_address] 
        if ts > cutoff
    ]
    
    if len(llm_request_tracker[ip_address]) >= RATE_LIMIT_MAX_CALLS:
        raise GuardrailViolation("Rate limit exceeded for LLM calls")
    
    llm_request_tracker[ip_address].append(now)

def validate_output(response: str, expected_format: str = None) -> bool:
    """
    Validate the output of the LLM
    """
    if not response or not isinstance(response, str):
        return False
    
    if len(response.strip()) == 0:
        return False
    
    if expected_format == 'json':
        try:
            json.loads(response)
            return True
        except json.JSONDecodeError:
            return False
    
    inappropriate_indicators = [
        'sorry, i cannot',
        'i cannot help',
        'inappropriate',
        'offensive',
        'harmful',
        'illegal',
        'unethical'
    ]
    
    response_lower = response.lower()
    for indicator in inappropriate_indicators:
        if indicator in response_lower:
            logger.warning(f"LLM refused or flagged content: {indicator}")
            return False
    
    return True

def filter_content(query: str) -> bool:
    """
    Filter the query to ensure it is food-related
    """
    food_domain_keywords = [
        'recipe', 'food', 'cook', 'ingredient', 'meal', 'dish', 'eat',
        'bake', 'cuisine', 'flavor', 'taste', 'spice', 'vegetable', 
        'fruit', 'meat', 'protein', 'grain', 'dairy', 'dessert',
        'breakfast', 'lunch', 'dinner', 'snack', 'healthy', 'diet',
        'vegan', 'vegetarian', 'gluten', 'chicken', 'beef', 'pork',
        'fish', 'seafood', 'pasta', 'rice', 'bread', 'cheese', 'egg',
        'milk', 'butter', 'oil', 'sugar', 'salt', 'pepper', 'tomato',
        'onion', 'garlic', 'potato', 'carrot', 'soup', 'salad', 'sauce',
        'pizza', 'burger', 'sandwich', 'cake', 'cookie', 'pie'
    ]
    
    query_lower = query.lower()
    words = query_lower.split()
    
    off_topic_indicators = [
        'weather', 'temperature', 'forecast', 'rain', 'sunny',
        'math', 'calculate', 'solve', 'equation', 'problem',
        'poem', 'story', 'write', 'essay', 'article',
        'president', 'politics', 'government', 'election',
        'stock', 'market', 'investment',
        'movie', 'film', 'song', 'music', 'game',
        'sports', 'football', 'basketball', 'soccer'
    ]
    
    for indicator in off_topic_indicators:
        if indicator in query_lower:
            return False
    
    for word in words:
        if len(word) > 2 and word in food_domain_keywords:
            return True
    
    for keyword in food_domain_keywords:
        if keyword in query_lower:
            return True
    
    common_food_phrases = [
        'what can i', 'i have', 'i want', 'show me', 'find me',
        'looking for', 'need a', 'make with', 'to cook'
    ]
    
    for phrase in common_food_phrases:
        if phrase in query_lower:
            return True
    
    return False

def understand_query(query: str, ip_address: str = None) -> Optional[Dict[str, Any]]:
    """
    Understand the user's query and extract structured information
    """
    try:
        validate_input(query, ip_address)
        
        if not llm_client.is_available():
            logger.debug("LLM not available, skipping query understanding")
            return None
        
        system_prompt = """You are a food and recipe understanding assistant. Extract structured information from user queries.

Output ONLY valid JSON with this exact format:
{
  "keywords": ["list", "of", "food", "keywords"],
  "excluded_ingredients": ["ingredients", "to", "exclude"],
  "dietary_preferences": ["vegan", "gluten-free", etc],
  "cuisine_type": "italian/mexican/asian/etc or empty string",
  "meal_type": "breakfast/lunch/dinner/snack or empty string"
}

Rules:
- Only extract food-related keywords
- Detect exclusions from phrases like "no dairy", "without eggs", "I'm allergic to nuts"
- Identify dietary preferences
- Return empty arrays if nothing found
- Keep it concise"""

        user_prompt = f"Extract information from this food query: '{query}'"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response = llm_client.call(messages, temperature=0.2, max_tokens=300)
        
        if not response:
            return None
        
        if not validate_output(response, expected_format='json'):
            logger.warning("Invalid LLM response format")
            return None
        
        try:
            parsed = json.loads(response)
            
            required_keys = ['keywords', 'excluded_ingredients', 'dietary_preferences', 'cuisine_type', 'meal_type']
            if not all(key in parsed for key in required_keys):
                logger.warning("Missing required keys in LLM response")
                return None
            
            logger.info(f"Query understanding successful: {parsed}")
            return parsed
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON response: {e}")
            return None
            
    except GuardrailViolation as e:
        logger.warning(f"Guardrail violation: {e}")
        return None
    except Exception as e:
        logger.error(f"Error in query understanding: {e}")
        return None

def extract_excluded_ingredients(query: str, ip_address: str = None) -> Optional[List[str]]:
    """
    Extract excluded ingredients from the query
    """
    try:
        validate_input(query, ip_address)
        
        if not llm_client.is_available():
            logger.debug("LLM not available, skipping ingredient extraction")
            return None
        
        system_prompt = """You are a dietary restriction and allergen detection assistant. 

Extract ingredients that should be EXCLUDED from recipes based on the user's query.

Output ONLY valid JSON array format:
["ingredient1", "ingredient2", "ingredient3"]

Detect exclusions from:
- "no X", "without X", "exclude X"
- "allergic to X", "intolerant to X"
- "can't eat X", "cannot have X"
- "X-free" (dairy-free, gluten-free, etc)
- Health conditions implying exclusions

Expand common allergens:
- "dairy" includes: milk, cheese, butter, cream, yogurt
- "gluten" includes: wheat, barley, rye
- "nuts" includes: peanuts, almonds, cashews, walnuts

Return empty array [] if no exclusions found."""

        user_prompt = f"What ingredients should be excluded from this query: '{query}'"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response = llm_client.call(messages, temperature=0.1, max_tokens=200)
        
        if not response:
            return None
        
        if not validate_output(response, expected_format='json'):
            logger.warning("Invalid ingredient extraction response")
            return None
        
        try:
            excluded = json.loads(response)
            
            if not isinstance(excluded, list):
                return None
            
            excluded = [item.lower().strip() for item in excluded if isinstance(item, str)]
            
            logger.info(f"Extracted excluded ingredients: {excluded}")
            return excluded
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse ingredient extraction JSON: {e}")
            return None
            
    except GuardrailViolation as e:
        logger.warning(f"Guardrail violation in ingredient extraction: {e}")
        return None
    except Exception as e:
        logger.error(f"Error in ingredient extraction: {e}")
        return None

def check_food_relevance(word: str) -> Optional[bool]:
    """
    Check if the word is food-related
    """
    if not llm_client.is_available():
        return None
    
    if len(word) < 2 or len(word) > 50:
        return False
    
    try:
        system_prompt = """You are a food relevance classifier. Determine if a word is related to food, cooking, ingredients, or cuisine.

Output ONLY 'yes' or 'no' (lowercase, one word)."""

        user_prompt = f"Is this word food-related: '{word}'"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response = llm_client.call(messages, temperature=0.1, max_tokens=10)
        
        if not response:
            return None
        
        response_clean = response.strip().lower()
        
        if response_clean == 'yes':
            return True
        elif response_clean == 'no':
            return False
        else:
            return None
            
    except Exception as e:
        logger.error(f"Error checking food relevance: {e}")
        return None

