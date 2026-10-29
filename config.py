"""AegisFlow configuration and startup validation.

All credentials are read from environment variables. Nothing is hardcoded and
``Settings.describe()`` never returns secret values.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env", override=False)

Mode = Literal["mock", "real"]
Provider = Literal["openrouter", "gemini", "openai"]

# Prefixes accepted in AEGISFLOW_MODEL for per-entry provider routing.
PROVIDER_ALIASES = {
    "openrouter": "openrouter",
    "gemini": "gemini",
    "google": "gemini",
    "openai": "openai",
}


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {value!r}") from exc


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {value!r}") from exc


@dataclass(frozen=True)
class Settings:
    """Runtime settings.

    ``mode='mock'`` is the safe default. Real mode requires an explicit
    acknowledgement (``AEGISFLOW_ALLOW_EXTERNAL_LLM=true``), a provider, a
    model, and the provider key.
    """

    mode: Mode = "mock"
    provider: Provider = "gemini"
    model: str = ""
    openrouter_api_key: str = ""
    google_api_key: str = ""
    openai_api_key: str = ""
    allow_external_llm: bool = False
    data_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data")
    max_file_mb: float = 10.0
    max_retries: int = 2
    max_revisions: int = 2
    max_delegation_depth: int = 3
    recursion_limit: int = 80
    app_db_name: str = "aegisflow.sqlite"
    checkpoint_db_name: str = "checkpoints.sqlite"
    skills_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "skills")
    warnings: tuple[str, ...] = field(default_factory=tuple)
    fallback_reason: str | None = None

    # ------------------------------------------------------------------ paths
    @property
    def app_db_path(self) -> Path:
        return self.data_dir / self.app_db_name

    @property
    def checkpoint_db_path(self) -> Path:
        return self.data_dir / self.checkpoint_db_name

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def simulated(self) -> bool:
        return self.mode == "mock"

    # -------------------------------------------------------------- factories
    @classmethod
    def from_env(cls) -> Settings:
        data_dir = Path(os.getenv("AEGISFLOW_DATA_DIR", "data"))
        if not data_dir.is_absolute():
            data_dir = PROJECT_ROOT / data_dir

        mode = os.getenv("AEGISFLOW_MODE", "mock").strip().lower()
        if mode not in {"mock", "real"}:
            raise ValueError("AEGISFLOW_MODE must be 'mock' or 'real'")

        provider = os.getenv("AEGISFLOW_PROVIDER", "gemini").strip().lower()
        if provider not in {"openrouter", "gemini", "openai"}:
            raise ValueError("AEGISFLOW_PROVIDER must be openrouter, gemini, or openai")

        settings = cls(
            mode=mode,  # type: ignore[arg-type]
            provider=provider,  # type: ignore[arg-type]
            model=os.getenv("AEGISFLOW_MODEL", "").strip(),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
            google_api_key=(
                os.getenv("GOOGLE_API_KEY", "").strip()
                or os.getenv("GEMINI_API_KEY", "").strip()
            ),
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            allow_external_llm=_env_bool("AEGISFLOW_ALLOW_EXTERNAL_LLM", False),
            data_dir=data_dir,
            max_file_mb=_env_float("AEGISFLOW_MAX_FILE_MB", 10.0),
            max_retries=_env_int("AEGISFLOW_MAX_RETRIES", 2),
            max_revisions=_env_int("AEGISFLOW_MAX_REVISIONS", 2),
            max_delegation_depth=_env_int("AEGISFLOW_MAX_DELEGATION_DEPTH", 3),
            recursion_limit=_env_int("AEGISFLOW_RECURSION_LIMIT", 80),
        )
        return settings.validate()

    def validate(self) -> Settings:
        warnings: list[str] = []
        fallback_reason: str | None = None
        mode = self.mode

        if self.max_file_mb <= 0:
            raise ValueError("AEGISFLOW_MAX_FILE_MB must be positive")
        if self.max_retries < 0:
            raise ValueError("AEGISFLOW_MAX_RETRIES cannot be negative")
        if self.max_revisions < 0:
            raise ValueError("AEGISFLOW_MAX_REVISIONS cannot be negative")
        if self.max_delegation_depth < 1:
            raise ValueError("AEGISFLOW_MAX_DELEGATION_DEPTH must be at least 1")
        if self.recursion_limit < 10:
            raise ValueError("AEGISFLOW_RECURSION_LIMIT must be at least 10")

        # An ambiguous model list must never be resolved by guessing: give up on
        # real mode so no request can reach a provider the operator did not name.
        try:
            self.model_candidates()
        except ValueError as exc:
            warnings.append(f"{exc} Falling back to mock mode.")
            fallback_reason = str(exc)
            mode = "mock"

        if mode == "real":
            key = self.api_key_for(self.provider)
            if not self.allow_external_llm:
                warnings.append(
                    "Real mode requested but AEGISFLOW_ALLOW_EXTERNAL_LLM is not true. "
                    "Falling back to mock mode so documents are not sent externally."
                )
                fallback_reason = "External LLM use was not authorized."
                mode = "mock"
            elif not key:
                warnings.append(
                    f"Real mode requested but no API key is configured for {self.provider}. "
                    "Falling back to mock mode."
                )
                fallback_reason = f"Missing API key for {self.provider}."
                mode = "mock"
            elif not self.model:
                warnings.append(
                    "Real mode requested but AEGISFLOW_MODEL is empty. "
                    "Falling back to mock mode."
                )
                fallback_reason = "AEGISFLOW_MODEL is empty."
                mode = "mock"

        if mode == "mock":
            warnings.append(
                "SIMULATED MODE: every agent result is deterministic mock output, "
                "not real AI analysis."
            )

        return Settings(
            mode=mode,  # type: ignore[arg-type]
            provider=self.provider,
            model=self.model,
            openrouter_api_key=self.openrouter_api_key,
            google_api_key=self.google_api_key,
            openai_api_key=self.openai_api_key,
            allow_external_llm=self.allow_external_llm,
            data_dir=self.data_dir,
            max_file_mb=self.max_file_mb,
            max_retries=self.max_retries,
            max_revisions=self.max_revisions,
            max_delegation_depth=self.max_delegation_depth,
            recursion_limit=self.recursion_limit,
            app_db_name=self.app_db_name,
            checkpoint_db_name=self.checkpoint_db_name,
            skills_dir=self.skills_dir,
            warnings=tuple(warnings),
            fallback_reason=fallback_reason,
        )

    def api_key_for(self, provider: str | None = None) -> str:
        provider = provider or self.provider
        if provider == "openrouter":
            return self.openrouter_api_key
        if provider in {"gemini", "google"}:
            return self.google_api_key
        if provider == "openai":
            return self.openai_api_key
        return ""

    def model_candidates(self) -> tuple[tuple[str, str], ...]:
        """Ordered ``(provider, model)`` pairs parsed from ``AEGISFLOW_MODEL``.

        Entries are comma separated and the order is the failover order, so the
        first entry is the primary. ``provider:model`` selects a provider
        explicitly and always wins: ``openrouter:openai/gpt-4o`` sends
        ``openai/gpt-4o`` through OpenRouter. A bare id uses ``self.provider``.

        ``provider/model`` is still accepted when it names the configured
        provider (``openrouter/nvidia/x:free`` under ``provider=openrouter``),
        but a *different* provider behind a slash raises instead of silently
        rerouting. ``openai/gpt-4o`` reads just as plausibly as native OpenAI
        and as an OpenRouter model id, and guessing is how a request reaches a
        vendor the operator did not choose.
        """
        entries = [
            entry.strip() for entry in (self.model or "").split(",") if entry.strip()
        ]
        candidates: list[tuple[str, str]] = []
        for entry in entries:
            head, separator, tail = entry.partition(":")
            provider = PROVIDER_ALIASES.get(head.lower())
            if separator and tail and provider:
                candidates.append((provider, tail))
                continue

            head, separator, tail = entry.partition("/")
            provider = PROVIDER_ALIASES.get(head.lower())
            if separator and tail and provider:
                if provider != self.provider:
                    raise ValueError(
                        f"AEGISFLOW_MODEL entry {entry!r} is ambiguous: {head!r} "
                        f"is a provider prefix, so it routes to {provider!r}, not "
                        f"to the configured {self.provider!r}. Write "
                        f"{provider}:{tail} to use the {provider} provider, or "
                        f"{self.provider}:{entry} to pass {tail!r} to "
                        f"{self.provider} as a model id."
                    )
                candidates.append((provider, tail))
                continue

            candidates.append((self.provider, entry))
        return tuple(candidates)

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def describe(self) -> dict[str, object]:
        """Safe, secret-free description for the UI and audit log."""
        try:
            candidates = [
                f"{provider}:{model_id}"
                for provider, model_id in self.model_candidates()
            ]
        except ValueError:
            candidates = ["(invalid AEGISFLOW_MODEL, see the fallback reason)"]
        return {
            "mode": self.mode,
            "provider": self.provider,
            "model": self.model or "(not set)",
            "model_candidates": candidates,
            "external_llm_authorized": self.allow_external_llm,
            "api_key_configured": bool(self.api_key_for()),
            "max_file_mb": self.max_file_mb,
            "max_retries": self.max_retries,
            "max_revisions": self.max_revisions,
            "max_delegation_depth": self.max_delegation_depth,
            "recursion_limit": self.recursion_limit,
            "fallback_reason": self.fallback_reason,
        }
