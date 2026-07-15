FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE /app/
COPY src /app/src
COPY config /app/config

RUN pip install --no-cache-dir .

EXPOSE 8080

CMD ["python", "-m", "thoth_mcp"]
