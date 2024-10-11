FROM python:3.9-slim-buster

WORKDIR /app

COPY requirements.txt .

RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt

RUN python -c "import nltk; nltk.download('stopwords')"

COPY ../recipe_finder.py .
COPY ../recipes.json .
COPY ../templates templates/

EXPOSE 5000

ENV FLASK_APP=recipe_finder.py

CMD ["python", "recipe_finder.py"]