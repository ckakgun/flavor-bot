FROM python:3.9

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN python -c "import nltk; nltk.download('stopwords')"

COPY recipe_finder.py .
COPY recipes.json .
COPY templates/ templates/

EXPOSE 5000

ENV FLASK_APP=recipe_finder.py
ENV FLASK_RUN_HOST=0.0.0.0

CMD ["flask", "run"]