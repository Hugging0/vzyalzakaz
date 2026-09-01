FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
RUN python -c 'import tomllib; print("\n".join(tomllib.load(open("pyproject.toml", "rb"))["project"]["dependencies"]))' > /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && pip install -r /tmp/requirements.txt

COPY app ./app
RUN pip install --no-deps .

COPY alembic.ini ./
COPY migrations ./migrations
COPY config ./config

RUN mkdir -p /data && useradd --create-home --uid 10001 jobhunter && chown -R jobhunter:jobhunter /app /data
USER jobhunter

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-1}"]
