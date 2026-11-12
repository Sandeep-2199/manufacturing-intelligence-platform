FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app/backend
COPY backend/requirements.txt .
# The web service has no Spark jobs. Keep the local analytics dependency out of the image.
RUN sed '/^pyspark==/d' requirements.txt > /tmp/requirements-web.txt \
    && pip install --no-cache-dir -r /tmp/requirements-web.txt \
    && groupadd --system mip && useradd --system --gid mip mip
COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/scripts ./scripts
COPY frontend /app/frontend
USER mip
CMD ["sh", "-c", "python -m scripts.migrate && python -m scripts.bootstrap_admin && unset MIP_BOOTSTRAP_ADMIN_PASSWORD && exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --forwarded-allow-ips='*'"]
