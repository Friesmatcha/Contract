FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY backend ./backend
RUN python -m pip install --no-cache-dir .

RUN addgroup --system app \
    && adduser --system --ingroup app app \
    && mkdir -p /var/lib/contract-review/files \
    && chown -R app:app /app /var/lib/contract-review

USER app

EXPOSE 8000
