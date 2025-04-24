FROM python:3.9

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and templates
COPY main.py .
COPY src/ src/
COPY src/components/templates/ src/components/templates/

# Create logs directory
RUN mkdir -p logs

# Copy env file if exists
COPY .env* .

EXPOSE 5001

ENV FLASK_APP=main.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=5001

CMD ["python", "main.py"]