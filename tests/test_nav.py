"""The signed-in username in the nav links to gatekeeper's account page."""

from types import SimpleNamespace

from flask import Flask
from flask.testing import FlaskClient


def test_username_links_to_whoami_fallback(client: FlaskClient) -> None:
    html = client.get("/admin/queue/").get_data(as_text=True)
    assert '<a href="/gatekeeper/auth/whoami" title="Your account">tester</a>' in html
    assert "<small>tester</small>" not in html
    # logout lives on the account page, as in gatekeeper's own nav
    assert "Logout" not in html


def test_whoami_derived_from_login_url(app: Flask, client: FlaskClient) -> None:
    app.config["GATEKEEPER_CLIENT"] = SimpleNamespace(
        get_login_url=lambda: "https://reports.example.com/gatekeeper/auth/login"
    )
    html = client.get("/admin/queue/").get_data(as_text=True)
    assert 'href="https://reports.example.com/gatekeeper/auth/whoami"' in html
