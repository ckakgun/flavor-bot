# Local Flavor Bot 🍳

Local Flavor Bot is a recipe recommendation chatbot that suggests recipes based on ingredients or dish preferences. The bot uses the Spoonacular API for recipe data and implements semantic search for better results.

## Features and Live Demo
You can try out the live version of the Local Flavor Bot here: https://flavorbot.akgns.com/

## Screenshots
### Web Interface
![Web Interface](assets/web_interface.png)

### Recipe Search Results
![Recipe Results](assets/recipe_results.png)

### CLI Interface
![CLI Interface](assets/cli_interface.png)

- Web UI for easy search
- Semantic search by using transformer models
- Rate limiting to prevent API abuse
- Detailed recipe information including:
    - Time
    - Servings
    - Ingredients list
    - Instructions
    - Source URL

## Setup

1. Clone the repository:
```bash
git clone [repository-url]
cd flavor-bot
```

2. Create a virtual env and activate it:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install required packages:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file in the project root and add your Spoonacular API key:
```
API_KEY=your_spoonacular_api_key_here
```

## Usage

### Web Interface (Default)
Run the application:
```bash
python recipe_finder.py
```
Then open your browser to navigate to the web interface.

### Installation

#### Using Virtual Environment

1. Clone the repository: `git clone https://github.com/ckakgun/flavor-bot.git`

    `cd flavor-bot`

2. Create and activate a virtual environment: 
    * `python -m venv` 
    * `venv source venv/bin/activate` 
    >  On Windows, use `venv\Scripts\activate`


3. Install the required packages: `pip install -r requirements.txt`

4. Run the application: `python recipe_finder.py`

5. The application should now be running on `http://localhost:5000`.

#### Using Docker
1) Build flavor-bot : `docker build -t flavor-bot:latest -f docker/Dockerfile .`
2) Run image : `docker run -p 5000:5000 -it flavor-bot`


### Example Queries
- "Show me some pasta recipes"
- "Vegetarian dinner ideas"
- "What can I cook with potatoes and cheese?"
- "Quick dinner recipes under 30 minutes"
- "Italian pasta dishes"

## Rate Limiting
The application includes rate limiting to prevent excessive API usage:
- Maximum 5 requests per 5 seconds per IP address (Local rate limiting)
- Maximum 150 requests per day (Spoonacular API limit)
- When the daily API limit is reached, users will be notified
- Applies to both web and CLI interfaces

> **Note**: The Spoonacular API has a daily limit of 150 requests with the free tier. Once this limit is reached, the application will notify users to try again the next day.

## Dependencies
- Flask for web interface
- Sentence Transformers for semantic search
- Requests for API calls
- Python-dotenv for environment variables
- PyTorch for tensor operations

## License
MIT License
