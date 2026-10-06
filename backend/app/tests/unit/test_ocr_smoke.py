"""Smoke-command tests (Stage 18).

All paths run offline: NOT_CONFIGURED with no key, SUCCESS and
FAILURE through an injected MockTransport client. No network, no
key, no database. The live provider is exercised only by a human
running the command with a real key, never by test discovery.
"""

import httpx

from app.cli import ocr_provider_smoke as smoke


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _ok(request):
    return httpx.Response(200, json={
        "IsErroredOnProcessing": False,
        "ParsedResults": [{
            "ParsedText": "Sodium Benzoate (E211)",
            "MeanTextConf": 91,
        }],
    })


def _fail(request):
    return httpx.Response(200, json={
        "IsErroredOnProcessing": True,
        "ErrorMessage": ["Invalid API key"],
    })


def test_not_configured_without_key(monkeypatch, capsys):
    monkeypatch.delenv("OCR_SPACE_API_KEY", raising=False)
    monkeypatch.setattr(
        "app.config.settings.ocr_space_api_key", "", raising=False)
    code = smoke.main([])
    assert code == smoke.EXIT_NOT_CONFIGURED
    out = capsys.readouterr().out
    assert "NOT_CONFIGURED" in out


def test_success_prints_only_safe_metadata(monkeypatch, capsys):
    monkeypatch.setenv("OCR_SPACE_API_KEY", "dummy-key-for-test")
    code = smoke.main(["--pipeline"], client=_client(_ok))
    assert code == smoke.EXIT_OK
    out = capsys.readouterr().out
    assert "status: SUCCESS" in out
    assert "text_length: 22" in out
    assert "confidence: 0.9100" in out
    assert "pipeline_nodes: 1" in out
    assert "dummy-key-for-test" not in out
    assert "Sodium Benzoate" not in out


def test_failure_reports_category_without_secrets(
    monkeypatch, capsys
):
    monkeypatch.setenv("OCR_SPACE_API_KEY", "dummy-key-for-test")
    code = smoke.main([], client=_client(_fail))
    assert code == smoke.EXIT_FAILURE
    out = capsys.readouterr().out
    assert "status: FAILURE" in out
    assert "category:" in out
    assert "dummy-key-for-test" not in out


def test_unreadable_image_is_a_clean_error(monkeypatch, capsys):
    monkeypatch.setenv("OCR_SPACE_API_KEY", "dummy-key-for-test")
    code = smoke.main(["--image", "/nonexistent-label.png"])
    assert code == smoke.EXIT_NOT_CONFIGURED
    out = capsys.readouterr().out
    assert "BAD_ARGUMENTS" in out


def test_provider_result_feeds_pipeline_unchanged(
    monkeypatch, capsys
):
    # The smoke pipeline path parses with the frozen parser only;
    # recognition quality is the provider's business, chemistry
    # still requires the registry + V1-V7 downstream.
    monkeypatch.setenv("OCR_SPACE_API_KEY", "dummy-key-for-test")
    code = smoke.main(["--pipeline", "--document-id", "doc-x"],
                      client=_client(_ok))
    assert code == smoke.EXIT_OK
    assert "pipeline_status: complete" in capsys.readouterr().out
