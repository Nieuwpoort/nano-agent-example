# syntax=docker/dockerfile:1.4
FROM python:3.11-slim

WORKDIR /app

RUN --mount=type=cache,target=/var/cache/apt \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip setuptools wheel

COPY docker/requirements-core.txt /app/requirements-core.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r /app/requirements-core.txt

COPY . /app

EXPOSE 7860

CMD ["python", "-u", "app.py"]
