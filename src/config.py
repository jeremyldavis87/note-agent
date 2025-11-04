from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def _load_env() -> None:
    # Load .env first if present, otherwise .env.local fallback
    cwd = Path(__file__).resolve().parent.parent
    candidates = [cwd / ".env", cwd / ".env.local"]
    for env_path in candidates:
        if env_path.exists():
            load_dotenv(env_path, override=False)
    # Also load from project root if executed differently
    root_candidates = [Path.cwd() / ".env", Path.cwd() / ".env.local"]
    for env_path in root_candidates:
        if env_path.exists():
            load_dotenv(env_path, override=False)


@dataclass
class Settings:
    # AI/LLM
    OPENAI_API_KEY: Optional[str]
    ANTHROPIC_API_KEY: Optional[str]
    BRAINTRUST_API_KEY: Optional[str]

    TEXT_AI_MODEL: str
    TEXT_AI_MODEL_VERBOSITY: str
    TEXT_AI_MODEL_REASONING: str
    TEXT_AI_MODEL_MAX_OUTPUT_TOKENS: int

    AGENT_VISION_MODEL: str
    AGENT_VISION_MODEL_VERBOSITY: str
    AGENT_VISION_MODEL_REASONING: str
    AGENT_VISION_MODEL_MAX_OUTPUT_TOKENS: int

    AGENT_OCR_CONFIDENCE_THRESHOLD: int
    AGENT_PROCESSING_TIMEOUT: int
    AGENT_PARALLEL_PROCESSING_LIMIT: int
    AGENT_MAX_RETRIES: int
    AGENT_ENABLE_BRAINTRUST: bool
    AGENT_ENABLE_JUDGE: bool
    AGENT_ENABLE_LOCAL_LOGS: bool

    # Files
    UPLOAD_DIR: str
    MAX_FILE_SIZE: int

    # Dev
    DEBUG: bool
    LOG_LEVEL: str

    @property
    def use_openai(self) -> bool:
        return bool(self.OPENAI_API_KEY)

    @property
    def use_anthropic(self) -> bool:
        return bool(self.ANTHROPIC_API_KEY)


def load_settings() -> Settings:
    _load_env()

    def _get_bool(name: str, default: str = "false") -> bool:
        return str(os.getenv(name, default)).lower() in {"1", "true", "yes", "y"}

    def _get_int(name: str, default: int) -> int:
        try:
            return int(os.getenv(name, str(default)))
        except ValueError:
            return default

    return Settings(
        OPENAI_API_KEY=os.getenv("OPENAI_API_KEY"),
        ANTHROPIC_API_KEY=os.getenv("ANTHROPIC_API_KEY"),
        BRAINTRUST_API_KEY=os.getenv("BRAINTRUST_API_KEY"),
        TEXT_AI_MODEL=os.getenv("TEXT_AI_MODEL", "gpt-4o-mini"),
        TEXT_AI_MODEL_VERBOSITY=os.getenv("TEXT_AI_MODEL_VERBOSITY", "low"),
        TEXT_AI_MODEL_REASONING=os.getenv("TEXT_AI_MODEL_REASONING", "low"),
        TEXT_AI_MODEL_MAX_OUTPUT_TOKENS=_get_int("TEXT_AI_MODEL_MAX_OUTPUT_TOKENS", 1000),
        AGENT_VISION_MODEL=os.getenv("AGENT_VISION_MODEL", "gpt-4o-mini"),
        AGENT_VISION_MODEL_VERBOSITY=os.getenv("AGENT_VISION_MODEL_VERBOSITY", "low"),
        AGENT_VISION_MODEL_REASONING=os.getenv("AGENT_VISION_MODEL_REASONING", "low"),
        AGENT_VISION_MODEL_MAX_OUTPUT_TOKENS=_get_int("AGENT_VISION_MODEL_MAX_OUTPUT_TOKENS", 1000),
        AGENT_OCR_CONFIDENCE_THRESHOLD=_get_int("AGENT_OCR_CONFIDENCE_THRESHOLD", 85),
        AGENT_PROCESSING_TIMEOUT=_get_int("AGENT_PROCESSING_TIMEOUT", 30),
        AGENT_PARALLEL_PROCESSING_LIMIT=_get_int("AGENT_PARALLEL_PROCESSING_LIMIT", 4),
        AGENT_MAX_RETRIES=_get_int("AGENT_MAX_RETRIES", 1),
        AGENT_ENABLE_BRAINTRUST=_get_bool("AGENT_ENABLE_BRAINTRUST", "false"),
        AGENT_ENABLE_JUDGE=_get_bool("AGENT_ENABLE_JUDGE", "false"),
        AGENT_ENABLE_LOCAL_LOGS=_get_bool("AGENT_ENABLE_LOCAL_LOGS", "true"),
        UPLOAD_DIR=os.getenv("UPLOAD_DIR", "./uploads"),
        MAX_FILE_SIZE=_get_int("MAX_FILE_SIZE", 10 * 1024 * 1024),
        DEBUG=_get_bool("DEBUG", "false"),
        LOG_LEVEL=os.getenv("LOG_LEVEL", "INFO"),
    )


settings = load_settings()
