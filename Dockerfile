FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY ai_assignment/ /app/

RUN python manage.py collectstatic --no-input

EXPOSE 8000

CMD ["gunicorn", "ai_assignment.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
