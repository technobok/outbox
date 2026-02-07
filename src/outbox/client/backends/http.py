"""HTTP API backend for OutboxClient (remote server)."""

import base64

import httpx

from outbox.client.models import Message, MessageResult


class HttpBackend:
    """Backend that communicates with a remote Outbox server via JSON API."""

    def __init__(self, server_url: str, api_key: str, timeout: float = 30.0) -> None:
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.server_url,
            headers={"X-API-Key": self.api_key},
            timeout=self.timeout,
        )

    def submit_message(self, message: Message) -> MessageResult:
        payload: dict = {
            "from_address": message.from_address,
            "to": message.to,
            "subject": message.subject,
            "body": message.body,
            "body_type": message.body_type,
            "delivery_type": message.delivery_type,
        }
        if message.cc:
            payload["cc"] = message.cc
        if message.bcc:
            payload["bcc"] = message.bcc
        if message.source_app:
            payload["source_app"] = message.source_app
        if message.attachments:
            payload["attachments"] = [
                {
                    "filename": att.filename,
                    "content_type": att.content_type,
                    "content_base64": base64.b64encode(att.data).decode("ascii"),
                }
                for att in message.attachments
            ]

        with self._client() as client:
            resp = client.post("/api/v1/messages", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return MessageResult(
                uuid=data["uuid"],
                status=data["status"],
                created_at=data.get("created_at"),
            )

    def get_status(self, uuid: str) -> MessageResult | None:
        with self._client() as client:
            resp = client.get(f"/api/v1/messages/{uuid}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            return MessageResult(
                uuid=data["uuid"],
                status=data["status"],
                created_at=data.get("created_at"),
                updated_at=data.get("updated_at"),
                sent_at=data.get("sent_at"),
                last_error=data.get("last_error"),
            )

    def list_messages(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MessageResult]:
        params: dict = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status

        with self._client() as client:
            resp = client.get("/api/v1/messages", params=params)
            resp.raise_for_status()
            data = resp.json()
            return [
                MessageResult(
                    uuid=m["uuid"],
                    status=m["status"],
                    created_at=m.get("created_at"),
                    updated_at=m.get("updated_at"),
                    sent_at=m.get("sent_at"),
                    last_error=m.get("last_error"),
                )
                for m in data.get("messages", [])
            ]

    def retry_message(self, uuid: str) -> MessageResult | None:
        with self._client() as client:
            resp = client.post(f"/api/v1/messages/{uuid}/retry")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            return MessageResult(uuid=data["uuid"], status=data["status"])

    def cancel_message(self, uuid: str) -> MessageResult | None:
        with self._client() as client:
            resp = client.post(f"/api/v1/messages/{uuid}/cancel")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            return MessageResult(uuid=data["uuid"], status=data["status"])
