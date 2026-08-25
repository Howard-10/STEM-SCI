FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STEM_SCI_REPOSITORY_ROOT=/app \
    STEM_SCI_STORAGE_DIR=/var/lib/stem-sci

WORKDIR /app/backend

COPY backend/pyproject.toml backend/README.md ./
COPY backend/src ./src
COPY data/catalogs ./../data/catalogs
COPY data/derived ./../data/derived

RUN python -m pip install --no-cache-dir ".[hybrid-retrieval]"

RUN mkdir -p /var/lib/stem-sci

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)"

CMD ["uvicorn", "stem_sci.main:app", "--host", "0.0.0.0", "--port", "8000"]
