FROM python:3.9

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY recipe_finder.py .
COPY templates/ templates/
COPY .env .

EXPOSE 5001

ENV FLASK_APP=recipe_finder.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=5001

CMD ["python", "recipe_finder.py"]