FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Cloud Run injects $PORT (default 8080)
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
