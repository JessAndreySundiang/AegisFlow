#!/usr/bin/env python3
"""One real structured call: proves which provider serves and what it cost.

Usage:
    python tools/smoke.py

Exits 0 when a candidate answers, 2 when the app is in mock mode (nothing was
sent), and 1 when every candidate fails. Costs one request per run, so it is a
manual check rather than part of CI.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ruff: noqa: E402  (project imports follow the sys.path bootstrap)

from pydantic import BaseModel

from aegisflow.services.llm_service import LLMError, RealLLMService
from config import Settings


class Ping(BaseModel):
    text: str


def main() -> int:
    settings = Settings.from_env()
    print(
        f"mode={settings.mode} provider={settings.provider} "
        f"timeout={settings.llm_timeout_s:g}s"
    )
    for provider, model in settings.model_candidates():
        print(f"  candidate: {provider}:{model}")

    if settings.mode != "real":
        reason = settings.fallback_reason or "no real provider configured"
        print(f"NOT RUN mock mode ({reason})")
        return 2

    service = RealLLMService(settings)
    started = time.perf_counter()
    try:
        result = service.structured(
            "smoke",
            Ping,
            "You are a smoke test. Reply with one short sentence.",
            {"task": "Say hello and name the model that answered."},
        )
    except LLMError as exc:
        print(f"FAIL {type(exc).__name__}: {exc}")
        return 1
    elapsed = int((time.perf_counter() - started) * 1000)

    print(f"served_by={service.active_provider}:{service.active_model}")
    print(f"latency_ms={elapsed}")
    if service.last_usage:
        usage = " ".join(f"{key}={value}" for key, value in sorted(service.last_usage.items()))
        print(f"usage={usage}")
    else:
        print("usage=none reported")
    if service.last_attempts:
        skipped = ", ".join(
            f"{attempt['provider']}:{attempt['model']} ({attempt['error']})"
            for attempt in service.last_attempts
        )
        print(f"skipped={skipped}")
    print(f"text={result.text[:120]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
