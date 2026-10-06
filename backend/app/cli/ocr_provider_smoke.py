"""Controlled OCR.space smoke command (Stage 18, manual only).

Proves the real adapter can talk to the real provider without
wiring live calls into any automated test:

    OCR_SPACE_API_KEY=... python -m app.cli.ocr_provider_smoke
        --image label.png [--document-id doc-1] [--pipeline]

Behavior:

* no key configured -> prints NOT_CONFIGURED and exits 2. No
  network touched, nothing claimed.
* provider reachable -> extracts, validates the OCRResult, prints
  ONLY safe metadata (provider, text length, confidence, overlay
  flag, failure category), exits 0. The key, the raw text, and
  the image bytes never appear in output, logs, or the database
  (this command never opens a database at all).
* provider failure -> prints the exact safe failure category,
  exits 1, persists nothing.

Exit codes: 0 success, 1 provider failure, 2 not configured or
bad arguments.

Use a small, non-private test image (a label already suitable
for project testing). Never upload personal, health, or client
material. A 1x1 PNG is embedded below for transport checks.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

__all__ = ["main", "run_smoke", "EXIT_OK", "EXIT_FAILURE",
           "EXIT_NOT_CONFIGURED"]

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_NOT_CONFIGURED = 2

# Deterministic 1x1 transparent PNG (transport fixture only -- it
# proves bytes reach the provider and a response parses; it says
# nothing about recognition quality on real labels).
TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000"
    "001f15c4890000000a49444154789c63000100000500010d0a2db400"
    "00000049454e44ae426082"
)


def _provider_from_env(client=None):
    import os as _os

    from app.config import settings
    from app.services.ocr_space import OCRSpaceProvider

    key = (
        _os.getenv("OCR_SPACE_API_KEY", "")
        or settings.ocr_space_api_key
    ).strip()
    if not key:
        return None
    return OCRSpaceProvider(
        key,
        endpoint=settings.ocr_space_endpoint,
        client=client,
    )


def run_smoke(*, provider, image_bytes, document_id,
              run_pipeline):
    """Execute one smoke extraction; return (exit_code, lines)."""
    import asyncio as _asyncio

    from app.services.ocr_provider import OCRDocument, ProviderFailure

    lines = []
    try:
        result = _asyncio.run(provider.extract(OCRDocument(
            document_id=document_id, content=image_bytes)))
    except ProviderFailure as exc:
        lines.append("status: FAILURE")
        lines.append("provider: %s" % provider.name)
        lines.append("category: %s" % str(exc))
        return EXIT_FAILURE, lines
    lines.append("status: SUCCESS")
    lines.append("provider: %s" % result.provider)
    lines.append("text_length: %d" % len(result.raw_text))
    lines.append("confidence: %s" % (
        "%.4f" % result.ocr_confidence
        if result.ocr_confidence is not None else "unknown"))
    lines.append("has_overlay: %s" % bool(
        (result.page_metadata or {}).get("has_overlay")))
    lines.append("failure_category: none")
    if run_pipeline:
        from app.services.ingredient_parser import (
            parse_label_ingredients,
        )
        from app.services.ingredient_normalizer import normalize_result

        parsed = parse_label_ingredients(result.raw_text or "")
        normalized = normalize_result(parsed)
        lines.append("pipeline_nodes: %d" % len(normalized.nodes))
        lines.append("pipeline_status: %s" % normalized.status)
        lines.append("pipeline_warnings: %d" % sum(
            len(node.warnings) for node in normalized.all_nodes()))
    return EXIT_OK, lines


def main(argv=None, client=None) -> int:
    parser = argparse.ArgumentParser(
        description="controlled OCR.space smoke test")
    parser.add_argument(
        "--image", default="",
        help="path to a small test image (default: embedded 1x1 PNG)")
    parser.add_argument(
        "--document-id", default="smoke-test",
        help="document id recorded on the extraction")
    parser.add_argument(
        "--pipeline", action="store_true",
        help="also run parse+normalize locally (no persistence)")
    args = parser.parse_args(argv)

    provider = _provider_from_env(client=client)
    if provider is None:
        print("status: NOT_CONFIGURED")
        print("hint: set OCR_SPACE_API_KEY to enable the smoke test")
        return EXIT_NOT_CONFIGURED
    if args.image:
        try:
            image_bytes = Path(args.image).read_bytes()
        except OSError as exc:
            print("status: BAD_ARGUMENTS")
            print("hint: cannot read image: %s"
                  % type(exc).__name__)
            return EXIT_NOT_CONFIGURED
    else:
        image_bytes = bytes(TINY_PNG)
    code, lines = run_smoke(
        provider=provider, image_bytes=image_bytes,
        document_id=args.document_id, run_pipeline=args.pipeline)
    for line in lines:
        # Defense in depth: the key must never reach output even if
        # a future code path interpolates it into a message.
        print(line.replace(_provider_key(), "***"))
    return code


def _provider_key() -> str:
    import os as _os

    from app.config import settings

    return (
        _os.getenv("OCR_SPACE_API_KEY", "")
        or settings.ocr_space_api_key
    ).strip()


if __name__ == "__main__":
    sys.exit(main())
