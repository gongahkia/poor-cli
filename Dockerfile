FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HAUS_RUNTIME_ROOT=/data/haus

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 \
  && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY uv.lock ./

RUN pip install --no-cache-dir .

EXPOSE 8080
CMD ["python", "-m", "uvicorn", "haus.chat_server:_reload_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
