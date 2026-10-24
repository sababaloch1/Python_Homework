FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY api ./api
COPY seed ./seed

EXPOSE 8000
# migrate -> seed -> serve (the seed is idempotent, so restarts are safe)
CMD ["sh", "-c", "alembic upgrade head && python -m seed.run_seed && uvicorn api.app.main:app --host 0.0.0.0 --port 8000"]
