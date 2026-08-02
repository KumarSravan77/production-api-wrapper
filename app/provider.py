import asyncio
from typing import Any, Dict

import httpx


class ProviderError(Exception):
    def __init__(self, status: int, code: str, message: str, retryable: bool) -> None:
        self.status, self.code, self.message, self.retryable = status, code, message, retryable


class OpenAIProvider:
    def __init__(self, client: httpx.AsyncClient, key: str, base_url: str, retries: int) -> None:
        self.client, self.key, self.base_url, self.retries = client, key, base_url, retries

    async def create_response(self, payload: Dict[str, Any], request_id: str) -> Dict[str, Any]:
        if not self.key:
            raise ProviderError(503, "provider_not_configured", "OPENAI_API_KEY is not configured", False)
        headers = {"Authorization": f"Bearer {self.key}", "X-Client-Request-Id": request_id}
        for attempt in range(self.retries + 1):
            try:
                response = await self.client.post(
                    f"{self.base_url}/responses", headers=headers, json=payload
                )
            except httpx.TimeoutException as exc:
                if attempt < self.retries:
                    await asyncio.sleep(0.25 * 2**attempt)
                    continue
                raise ProviderError(504, "provider_timeout", "The provider timed out", True) from exc
            except httpx.HTTPError as exc:
                raise ProviderError(502, "provider_unavailable", "The provider is unavailable", True) from exc
            if response.status_code in {429, 500, 502, 503, 504} and attempt < self.retries:
                await asyncio.sleep(0.25 * 2**attempt)
                continue
            if response.is_error:
                try:
                    detail = response.json().get("error", {})
                    message = detail.get("message", "The provider rejected the request")
                    code = detail.get("code") or detail.get("type") or "provider_error"
                except (ValueError, AttributeError):
                    code, message = "provider_error", "The provider rejected the request"
                status = response.status_code if response.status_code < 500 else 502
                raise ProviderError(status, str(code), str(message), response.status_code >= 500)
            return response.json()
        raise ProviderError(502, "provider_unavailable", "The provider is unavailable", True)
