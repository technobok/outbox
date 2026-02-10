"""Background queue worker - polls for messages and sends them via SMTP."""

import logging
import signal
import sys
import time
from datetime import UTC, datetime, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("outbox.worker")

_running = True


def _handle_signal(signum: int, frame: object) -> None:
    global _running
    log.info("Received signal %s, shutting down...", signum)
    _running = False


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


def run() -> None:
    """Main worker loop."""
    from outbox import create_app

    app = create_app()

    poll_interval = app.config["QUEUE_POLL_INTERVAL"]
    batch_size = app.config["QUEUE_BATCH_SIZE"]
    max_retries = app.config["QUEUE_MAX_RETRIES"]
    retry_base = app.config["QUEUE_RETRY_BASE_SECONDS"]
    retry_max = app.config["QUEUE_RETRY_MAX_SECONDS"]
    retention_days = app.config["RETENTION_DAYS"]

    log.info(
        "Worker started (poll=%ds, batch=%d, retries=%d, retention=%dd)",
        poll_interval,
        batch_size,
        max_retries,
        retention_days,
    )

    while _running:
        with app.app_context():
            try:
                _process_batch(batch_size, max_retries, retry_base, retry_max)
                _purge_old(retention_days)
            except Exception:
                log.exception("Error in worker loop")

        # Sleep in small increments so we can respond to signals
        for _ in range(poll_interval * 10):
            if not _running:
                break
            time.sleep(0.1)

    log.info("Worker stopped.")


def _process_batch(
    batch_size: int,
    max_retries: int,
    retry_base: int,
    retry_max: int,
) -> None:
    """Process a batch of pending messages."""
    from outbox.models.message import Message
    from outbox.services.email_sender import send_message

    messages = Message.get_pending_batch(batch_size)
    if not messages:
        return

    log.info("Processing %d message(s)", len(messages))

    for message in messages:
        message.update_status("sending")
        log.info("Sending message %s to %s", message.uuid, message.to_list())

        try:
            send_message(message)
            message.update_status("sent")
            log.info("Message %s sent successfully", message.uuid)
        except Exception as exc:
            error_msg = str(exc)
            log.warning("Message %s failed: %s", message.uuid, error_msg)

            message.retries_remaining -= 1
            if message.retries_remaining > 0:
                # Exponential backoff: base * 2^(max - remaining), capped at max
                exponent = max_retries - message.retries_remaining
                delay = min(retry_base * (2**exponent), retry_max)
                next_retry = (datetime.now(UTC) + timedelta(seconds=delay)).isoformat()
                message.update_status("failed", last_error=error_msg, next_retry_at=next_retry)
                log.info(
                    "Message %s will retry in %ds (%d retries remaining)",
                    message.uuid,
                    delay,
                    message.retries_remaining,
                )
            else:
                message.update_status("dead", last_error=error_msg)
                log.warning("Message %s is dead (no retries left)", message.uuid)


def _purge_old(retention_days: int) -> None:
    """Purge old sent/dead messages beyond retention period."""
    from outbox.models.message import Message

    purged = Message.purge_old(retention_days)
    if purged > 0:
        log.info("Purged %d old message(s)", purged)


if __name__ == "__main__":
    run()
