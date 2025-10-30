from __future__ import annotations

from typing import Tuple

from ..config import settings
from .base import VisionLLMClient, TextLLMClient
from .openai_client import OpenAIVision, OpenAIText
from .anthropic_client import AnthropicVision, AnthropicText


def get_clients() -> Tuple[VisionLLMClient, TextLLMClient]:
    vision_client: VisionLLMClient
    text_client: TextLLMClient

    # Vision selection
    if settings.use_openai and settings.AGENT_VISION_MODEL.lower().startswith("gpt"):
        vision_client = OpenAIVision()
    elif settings.use_anthropic:
        vision_client = AnthropicVision()
    elif settings.use_openai:  # default to OpenAI if key exists
        vision_client = OpenAIVision()
    else:
        raise RuntimeError("No supported vision provider configured")

    # Text selection
    if settings.use_openai and settings.TEXT_AI_MODEL.lower().startswith("gpt"):
        text_client = OpenAIText()
    elif settings.use_anthropic:
        text_client = AnthropicText()
    elif settings.use_openai:
        text_client = OpenAIText()
    else:
        raise RuntimeError("No supported text provider configured")

    return vision_client, text_client


__all__ = ["get_clients"]
