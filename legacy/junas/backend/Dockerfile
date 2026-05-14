FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY api/ ./api/
COPY data/ ./data/
COPY ml/ ./ml/
COPY migrations/ ./migrations/

RUN pip install --no-cache-dir .

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
