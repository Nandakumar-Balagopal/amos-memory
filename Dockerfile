FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md config.yaml ./
COPY src ./src

RUN pip install --upgrade pip \
    && pip install -e .

EXPOSE 8080

CMD ["amos", "serve"]
