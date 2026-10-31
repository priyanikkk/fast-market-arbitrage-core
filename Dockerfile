FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY config.py main.py ./
COPY core ./core

RUN useradd --create-home --uid 10001 app
USER app

ENTRYPOINT ["python", "main.py"]
