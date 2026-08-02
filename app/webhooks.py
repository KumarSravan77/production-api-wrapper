import asyncio
import hashlib
import hmac
import json
import time
from typing import Any, Dict
from urllib.parse import urlparse

import httpx


def validate_webhook_url(url: str, allow_http: bool) -> None:
    parsed = urlparse(url)
    schemes = {"http", "https"} if allow_http else {"https"}
    if parsed.scheme not in schemes:
        raise ValueError("Webhook URL must use HTTPS")
    if parsed.hostname in {"localhost", "127.0.0.1", "::1"} and not allow_http:
        raise ValueError("Local webhook URLs are not allowed")


def sign_payload(body: bytes, timestamp: str, secret: str) -> str:
    return hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


async def deliver_webhook(
    client: httpx.AsyncClient, url: str, event: Dict[str, Any], secret: str
) -> None:
    body = json.dumps(event, separators=(",", ":"), sort_keys=True).encode()
    timestamp = str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Timestamp": timestamp,
        "X-Webhook-Signature": f"v1={sign_payload(body, timestamp, secret)}",
    }
    for attempt in range(3):
        try:
            response = await client.post(url, content=body, headers=headers)
            if response.status_code < 500:
                return
        except httpx.HTTPError:
            pass
        if attempt < 2:
            await asyncio.sleep(0.5 * 2**attempt)
