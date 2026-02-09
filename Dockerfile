FROM python:3.14-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl git gcc libldap2-dev libsasl2-dev && \
    rm -rf /var/lib/apt/lists/*

RUN pip install uv

WORKDIR /app

COPY pyproject.toml ./
COPY src/ src/
COPY database/ database/
COPY worker/ worker/
COPY wsgi.py ./
RUN mkdir -p instance

RUN uv pip install --system git+https://github.com/technobok/gatekeeper.git && \
    uv pip install --system --no-sources -e ".[dev]"

EXPOSE 5200

ENV OUTBOX_ROOT=/app

CMD ["gunicorn", "wsgi:app", "--bind", "0.0.0.0:5200", "--workers", "2", "--preload"]
