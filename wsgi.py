"""WSGI entry point for Outbox (gunicorn wsgi:app)."""

from outbox import create_app

app = create_app()
