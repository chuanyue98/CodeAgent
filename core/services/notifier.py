from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


def _webhook_urls(config: dict) -> list[str]:
    """Reads ``notifications.webhooks`` from config.json.

    Accepts either a single URL string or a list of URL strings so a
    one-webhook setup doesn't need to type an array.
    """
    raw = config.get("notifications", {})
    if not isinstance(raw, dict):
        return []
    urls = raw.get("webhooks", [])
    if isinstance(urls, str):
        return [urls] if urls else []
    if isinstance(urls, list):
        return [u for u in urls if isinstance(u, str) and u.strip()]
    return []


def notify(config: dict, event: str, payload: dict[str, Any]) -> None:
    """Best-effort POST of a JSON event to every configured webhook URL.

    Never raises — an unreachable or misconfigured webhook must not take
    down the scheduler tick loop or a task run. Failures are logged, not
    surfaced. No-op when ``notifications.webhooks`` isn't configured.
    """
    urls = _webhook_urls(config)
    if not urls:
        return

    body = json.dumps({"event": event, **payload}, default=str).encode("utf-8")
    for url in urls:
        try:
            request = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(request, timeout=5)  # noqa: S310
        except (urllib.error.URLError, OSError, ValueError):
            logger.warning(
                "Failed to deliver %s webhook notification to %s",
                event,
                url,
                exc_info=True,
            )
