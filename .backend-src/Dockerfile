FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .

# По умолчанию — шедулер. Разовые задачи: docker compose run --rm orders-fetcher python -u main.py backfill
CMD ["python", "-u", "main.py"]
