"""OCR.space provider adapter (Stage 17).

Why OCR.space: the free tier is reasonable for development, the
contract is one HTTPS POST with key-only authentication (no SDK,
no OAuth dance), and its response taxonomy maps cleanly onto
explicit failures -- invalid key, quota exhaustion, parseable
error messages, and empty results are all first-class fields in
the API, not guesses. Credentials come only from the environment
(`OCR_SPACE_API_KEY`); nothing is logged, returned, or persisted
beyond the OCR-layer fields of :class:`OCRResult`.

The adapter returns transcription only. OCR.space responses carry
no chemistry, and this module has no code path that could invent
any: text and confidence flow through, everything else is dropped.

Live calls are never made by tests: every test below the service
injects `httpx.MockTransport`, so the full failure taxonomy is
deterministic with no network and no key.
"""

from __future__ import annotations

import base64
from typing import Any, Dict, Mapping, Optional

import httpx

from app.services.ocr_provider import (
    OCRDocument,
    OCRResult,
    ProviderFailure,
)

__all__ = ["OCRSpaceProvider", "OCR_SPACE_DEFAULT_ENDPOINT"]

OCR_SPACE_DEFAULT_ENDPOINT = "https://api.ocr.space/parse/image"


class OCRSpaceProvider:
    """OCR.space adapter behind the injected provider protocol."""

    def __init__(
        self,
        api_key: str,
        *,
        name: str = "ocr-space",
        endpoint: str = OCR_SPACE_DEFAULT_ENDPOINT,
        timeout_seconds: float = 20.0,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        if not (api_key or "").strip():
            raise ValueError(
                "OCR.space API key is required "
                "(OCR_SPACE_API_KEY)")
        self._api_key = api_key.strip()
        self.name = name
        self._endpoint = endpoint
        self._timeout = timeout_seconds
        self._client = client

    async def extract(self, document: OCRDocument) -> OCRResult:
        payload = self._request_payload(document)
        client = self._client or httpx.AsyncClient(
            timeout=self._timeout)
        close = self._client is None
        try:
            try:
                response = await client.post(
                    self._endpoint, data=payload)
            except httpx.TimeoutException as exc:
                raise ProviderFailure(
                    "ocr.space request timed out: %s"
                    % type(exc).__name__)
            except httpx.HTTPError as exc:
                raise ProviderFailure(
                    "ocr.space network failure: %s"
                    % type(exc).__name__)
            if response.status_code == 429:
                raise ProviderFailure(
                    "ocr.space quota exhausted (HTTP 429)")
            if response.status_code >= 400:
                raise ProviderFailure(
                    "ocr.space HTTP error %d"
                    % response.status_code)
            try:
                body = response.json()
            except ValueError:
                raise ProviderFailure(
                    "ocr.space returned malformed JSON")
            return self._to_result(document, body)
        finally:
            if close:
                await client.aclose()

    def _request_payload(self, document: OCRDocument) -> Dict[str, Any]:
        content = getattr(document, "content", None)
        payload: Dict[str, Any] = {
            "apikey": self._api_key,
            "OCREngine": "2",
            "scale": "true",
        }
        if content:
            payload["base64Image"] = (
                "data:image/png;base64,"
                + base64.b64encode(bytes(content)).decode("ascii")
            )
        elif document.locator:
            payload["url"] = document.locator
        else:
            raise ProviderFailure(
                "ocr.space needs image content or a locator")
        return payload

    def _to_result(
        self, document: OCRDocument, body: Mapping[str, Any]
    ) -> OCRResult:
        if not isinstance(body, dict):
            raise ProviderFailure(
                "ocr.space returned a malformed response")
        if body.get("IsErroredOnProcessing"):
            message = body.get("ErrorMessage") or body.get(
                "ErrorDetails") or "processing error"
            text = " ".join(
                str(part) for part in (
                    message if isinstance(message, list)
                    else [message]
                )
            )
            lowered = text.lower()
            if "invalid" in lowered and "key" in lowered:
                raise ProviderFailure(
                    "ocr.space rejected the API key")
            if "max" in lowered and "request" in lowered:
                raise ProviderFailure(
                    "ocr.space quota exhausted")
            raise ProviderFailure(
                "ocr.space processing error: %s" % text[:200])
        results = body.get("ParsedResults") or []
        if not results or not isinstance(results, list):
            raise ProviderFailure(
                "ocr.space returned no parsed results")
        first = results[0] if isinstance(results[0], dict) else {}
        text = first.get("ParsedText") or ""
        confidence = _confidence(first.get("MeanTextConf"))
        metadata: Dict[str, Any] = {}
        if first.get("TextOverlay") is not None:
            metadata["has_overlay"] = True
        return OCRResult(
            document_id=document.document_id,
            provider=self.name,
            raw_text=str(text),
            ocr_confidence=confidence,
            page_metadata=metadata,
            source_reference={"ocr_space": True},
        )


def _confidence(value: object) -> Optional[float]:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if number != number or number < 0:
        return None
    if number > 100:
        return None
    return number / 100.0 if number > 1.0 else number
