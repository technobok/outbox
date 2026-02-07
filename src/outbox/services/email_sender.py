"""SMTP email sending service."""

import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import mistune
from flask import current_app

from outbox.models.attachment import Attachment
from outbox.models.message import Message


def _try_login(server: smtplib.SMTP, username: str, password: str) -> None:
    """Attempt SMTP login only if the server supports AUTH."""
    if not username or not password:
        return
    if server.has_extn("auth"):
        server.login(username, password)


def send_message(message: Message) -> None:
    """Send a message via SMTP.

    Raises an exception on failure so the caller can handle retries.
    """
    smtp_server = current_app.config["SMTP_SERVER"]
    smtp_port = current_app.config["SMTP_PORT"]
    smtp_use_tls = current_app.config["SMTP_USE_TLS"]
    smtp_username = current_app.config["SMTP_USERNAME"]
    smtp_password = current_app.config["SMTP_PASSWORD"]

    if not smtp_server:
        raise RuntimeError("SMTP_SERVER not configured")

    attachments = Attachment.get_for_message(message.id)

    # Build MIME message
    if attachments:
        msg = MIMEMultipart("mixed")
        body_part = _build_body(message)
        msg.attach(body_part)
        for att in attachments:
            att_part = _build_attachment(att)
            if att_part:
                msg.attach(att_part)
    else:
        msg = _build_body(message)

    msg["From"] = message.from_address
    msg["To"] = ", ".join(message.to_list())
    cc = message.cc_list()
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = message.subject

    # Collect all recipients
    all_recipients = message.to_list() + message.cc_list() + message.bcc_list()

    # Send
    if smtp_use_tls:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.ehlo()
            _try_login(server, smtp_username, smtp_password)
            server.sendmail(message.from_address, all_recipients, msg.as_string())
    else:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            _try_login(server, smtp_username, smtp_password)
            server.sendmail(message.from_address, all_recipients, msg.as_string())


def _build_body(message: Message) -> MIMEMultipart | MIMEText:
    """Build the body part of the email."""
    if message.body_type == "html":
        return MIMEText(message.body, "html", "utf-8")
    elif message.body_type == "markdown":
        html_body = str(mistune.html(message.body))
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(message.body, "plain", "utf-8"))
        alt.attach(MIMEText(html_body, "html", "utf-8"))
        return alt
    else:
        # plain text
        return MIMEText(message.body, "plain", "utf-8")


def _build_attachment(att: Attachment) -> MIMEApplication | None:
    """Build a MIME attachment from an Attachment record."""
    path = Path(att.disk_path)
    if not path.exists():
        return None

    with open(path, "rb") as f:
        data = f.read()

    part = MIMEApplication(data)
    part.add_header("Content-Disposition", "attachment", filename=att.filename)
    part.add_header("Content-Type", att.content_type)
    return part
