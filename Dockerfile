FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Some VPS networks advertise IPv6 in DNS without providing an IPv6 route.
# Prefer IPv4 so HTTP clients can reliably reach Telegram and public job APIs.
RUN printf 'precedence ::ffff:0:0/96 100\n' >> /etc/gai.conf

COPY pyproject.toml ./
COPY app ./app
RUN pip install --upgrade pip && pip install .

COPY alembic.ini ./
COPY migrations ./migrations
COPY config ./config

RUN mkdir -p /data && useradd --create-home --uid 10001 jobhunter && chown -R jobhunter:jobhunter /app /data
USER jobhunter

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-1}"]
