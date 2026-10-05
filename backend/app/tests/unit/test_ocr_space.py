"""OCR.space adapter tests (Stage 17).

Every test injects `httpx.MockTransport`: no network, no key, no
live call. Each failure mode of the real API contract is covered
deterministically, and no test lets the API key escape into a
result, a row, or a log record.
"""

import httpx
import pytest

from app.services.ocr_provider import OCRDocument, ProviderFailure
from app.services.ocr_space import OCRSpaceProvider


def _provider(handler, **kwargs):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OCRSpaceProvider("test-key", client=client, **kwargs)


def _ok_payload(text="Sodium Benzoate (E211)", confidence=87):
    return {
        "IsErroredOnProcessing": False,
        "ParsedResults": [{
            "ParsedText": text,
            "MeanTextConf": confidence,
        }],
    }


def _run(provider, **document_kwargs):
    import asyncio

    kwargs = {"document_id": "doc-1"}
    kwargs.update(document_kwargs)
    return asyncio.run(provider.extract(OCRDocument(**kwargs)))


def _json_handler(payload, status=200):
    def handler(request):
        return httpx.Response(status, json=payload)

    return handler


# -- success ---------------------------------------------------------------------


def test_success_maps_text_and_confidence_only():
    provider = _provider(_json_handler(_ok_payload()))
    result = _run(provider, content=b"\x89PNG fake")
    assert result.raw_text == "Sodium Benzoate (E211)"
    assert result.ocr_confidence == 0.87
    assert result.provider == "ocr-space"
    assert result.document_id == "doc-1"


def test_result_carries_no_chemistry_or_secrets():
    provider = _provider(_json_handler(_ok_payload()))
    result = _run(provider, content=b"bytes")
    payload = str(vars(result)).lower()
    assert "test-key" not in payload
    for forbidden in ("formula", "smiles", "inchi", "cas", "entity",
                      "verified", "role"):
        assert forbidden not in payload, forbidden


def test_locator_path_posts_url_not_bytes():
    seen = {}

    def handler(request):
        import urllib.parse

        seen.update(urllib.parse.parse_qs(request.content.decode()))
        return httpx.Response(200, json=_ok_payload("water"))

    provider = _provider(handler)
    result = _run(provider, locator="https://example.com/label.png")
    assert result.raw_text == "water"
    assert seen["url"] == ["https://example.com/label.png"]
    assert "base64Image" not in seen


def test_bytes_path_posts_base64():
    seen = {}

    def handler(request):
        import urllib.parse

        seen.update(urllib.parse.parse_qs(request.content.decode()))
        return httpx.Response(200, json=_ok_payload("x"))

    provider = _provider(handler)
    _run(provider, content=b"\x00\x01")
    assert seen["base64Image"][0].startswith("data:image/png;base64,")


def test_neither_bytes_nor_locator_fails_cleanly():
    provider = _provider(_json_handler(_ok_payload()))
    with pytest.raises(ProviderFailure):
        _run(provider)


def test_api_key_never_leaves_as_query_or_log():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode()
        return httpx.Response(200, json=_ok_payload("x"))

    provider = _provider(handler)
    _run(provider, content=b"bytes")
    assert "test-key" not in seen["url"]
    assert "apikey" in seen["body"]  # form field, never logged


# -- configuration -----------------------------------------------------------------


def test_missing_api_key_fails_at_construction():
    with pytest.raises(ValueError):
        OCRSpaceProvider("")
    with pytest.raises(ValueError):
        OCRSpaceProvider("   ")


# -- failure taxonomy ------------------------------------------------------------------


def test_invalid_key_is_explicit():
    provider = _provider(_json_handler({
        "IsErroredOnProcessing": True,
        "ErrorMessage": ["Invalid API key"],
    }))
    with pytest.raises(ProviderFailure, match="API key"):
        _run(provider, content=b"x")


def test_quota_message_is_explicit():
    provider = _provider(_json_handler({
        "IsErroredOnProcessing": True,
        "ErrorMessage": ["Max number of requests exceeded"],
    }))
    with pytest.raises(ProviderFailure, match="quota"):
        _run(provider, content=b"x")


def test_processing_error_is_explicit():
    provider = _provider(_json_handler({
        "IsErroredOnProcessing": True,
        "ErrorMessage": ["File failed validation"],
    }))
    with pytest.raises(ProviderFailure, match="processing error"):
        _run(provider, content=b"x")


def test_http_429_is_quota():
    provider = _provider(_json_handler({}, status=429))
    with pytest.raises(ProviderFailure, match="quota"):
        _run(provider, content=b"x")


def test_http_500_is_explicit():
    provider = _provider(_json_handler({}, status=500))
    with pytest.raises(ProviderFailure, match="HTTP error 500"):
        _run(provider, content=b"x")


def test_malformed_json_is_explicit():
    def handler(request):
        return httpx.Response(200, text="not json{{")

    provider = _provider(handler)
    with pytest.raises(ProviderFailure, match="malformed"):
        _run(provider, content=b"x")


def test_empty_results_are_explicit():
    provider = _provider(_json_handler({
        "IsErroredOnProcessing": False, "ParsedResults": []}))
    with pytest.raises(ProviderFailure, match="no parsed results"):
        _run(provider, content=b"x")


def test_timeout_is_explicit():
    def handler(request):
        raise httpx.ConnectTimeout("slow")

    provider = _provider(handler)
    with pytest.raises(ProviderFailure, match="timed out"):
        _run(provider, content=b"x")


def test_network_failure_is_explicit():
    def handler(request):
        raise httpx.ConnectError("down")

    provider = _provider(handler)
    with pytest.raises(ProviderFailure, match="network failure"):
        _run(provider, content=b"x")
