FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements-runtime.txt .
RUN pip install --no-cache-dir -r requirements-runtime.txt \
    && groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app
COPY src ./src
COPY sql ./sql
COPY migrations ./migrations
COPY alembic.ini .
USER app
EXPOSE 8000
CMD ["uvicorn", "src.runtime.api:app", "--host", "0.0.0.0", "--port", "8000"]
