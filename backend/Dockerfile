FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FASTEMBED_CACHE_PATH=/opt/fastembed

# UID 1000 is what Hugging Face Spaces runs containers as
RUN useradd -m -u 1000 appuser
WORKDIR /app

# Dependencies first, so this layer is cached until requirements.txt changes
COPY requirements.txt .
RUN pip install -r requirements.txt

# Bake the embedding model into the image (no download at runtime)
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')" \
    && chmod -R a+rX /opt/fastembed

COPY app ./app

# Writable folder for the SQLite file (data is lost when the container is replaced)
RUN mkdir -p /data && chown appuser /data
USER appuser

ENV DATABASE_URL=sqlite:////data/codeatlas.db
EXPOSE 7860

# Hosts inject $PORT (Render); Hugging Face Spaces expects 7860
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860} --proxy-headers --forwarded-allow-ips='*'"]