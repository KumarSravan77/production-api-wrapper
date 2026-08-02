import asyncio
from typing import Any, AsyncIterator, Dict

import httpx


class ProviderError(Exception):
    def __init__(self, status: int, code: str, message: str, retryable: bool) -> None:
        self.status, self.code, self.message, self.retryable = status, code, message, retryable


class GatewayProvider:
    def __init__(self, client: httpx.AsyncClient, key: str, base_url: str, retries: int) -> None:
        self.client, self.key, self.base_url, self.retries = client, key, base_url, retries

    async def create_response(self, payload: Dict[str, Any], request_id: str) -> Dict[str, Any]:
        return await self._post("responses", payload, request_id)

    async def create_chat_completion(
        self, payload: Dict[str, Any], request_id: str
    ) -> Dict[str, Any]:
        return await self._post("chat/completions", payload, request_id)

    async def stream(
        self, endpoint: str, payload: Dict[str, Any], request_id: str
    ) -> AsyncIterator[bytes]:
        if not self.key:
            raise ProviderError(
                503, "gateway_not_configured", "LLM_GATEWAY_API_KEY is not configured", False
            )
        headers = {"Authorization": f"Bearer {self.key}", "X-Client-Request-Id": request_id}
        try:
            async with self.client.stream(
                "POST", f"{self.base_url}/{endpoint}", headers=headers, json=payload
            ) as response:
                if response.is_error:
                    body = await response.aread()
                    self._raise_response_error(response, body)
                async for chunk in response.aiter_raw():
                    yield chunk
        except httpx.TimeoutException as exc:
            raise ProviderError(504, "gateway_timeout", "The LLM gateway timed out", True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                502, "gateway_unavailable", "The LLM gateway is unavailable", True
            ) from exc

    async def _post(
        self, endpoint: str, payload: Dict[str, Any], request_id: str
    ) -> Dict[str, Any]:
        if not self.key:
            raise ProviderError(
                503, "gateway_not_configured", "LLM_GATEWAY_API_KEY is not configured", False
            )
        headers = {"Authorization": f"Bearer {self.key}", "X-Client-Request-Id": request_id}
        for attempt in range(self.retries + 1):
            try:
                response = await self.client.post(
                    f"{self.base_url}/{endpoint}", headers=headers, json=payload
                )
            except httpx.TimeoutException as exc:
                if attempt < self.retries:
                    await asyncio.sleep(0.25 * 2**attempt)
                    continue
                raise ProviderError(
                    504, "provider_timeout", "The provider timed out", True
                ) from exc
            except httpx.HTTPError as exc:
                raise ProviderError(
                    502, "provider_unavailable", "The provider is unavailable", True
                ) from exc
            if response.status_code in {429, 500, 502, 503, 504} and attempt < self.retries:
                await asyncio.sleep(0.25 * 2**attempt)
                continue
            if response.is_error:
                self._raise_response_error(response, response.content)
            return response.json()
        raise ProviderError(502, "gateway_unavailable", "The LLM gateway is unavailable", True)

    @staticmethod
    def _raise_response_error(response: httpx.Response, body: bytes) -> None:
        try:
            detail = response.json().get("error", {})
            message = detail.get("message", "The LLM gateway rejected the request")
            code = detail.get("code") or detail.get("type") or "gateway_error"
        except (ValueError, AttributeError):
            code, message = "gateway_error", "The LLM gateway rejected the request"
        status = response.status_code if response.status_code < 500 else 502
        raise ProviderError(status, str(code), str(message), response.status_code >= 500)


# Backward-compatible import for deployments that extended the original adapter.
OpenAIProvider = GatewayProvider
