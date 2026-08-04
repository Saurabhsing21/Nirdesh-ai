FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system voxloom \
    && adduser --system --ingroup voxloom --home /app voxloom \
    && mkdir -p /data \
    && chown -R voxloom:voxloom /app /data

COPY pyproject.toml ./
COPY app ./app
RUN python -m pip install --upgrade pip \
    && python -m pip install .

USER voxloom

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=15s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
