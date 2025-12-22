FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
VOLUME ["/app/results", "/app/data/processed"]

ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "src.api.main:APP", "--host", "0.0.0.0", "--port", "8000"]
