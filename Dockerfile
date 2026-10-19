FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd --create-home appuser && mkdir -p data logs && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["uvicorn", "production_ai.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
