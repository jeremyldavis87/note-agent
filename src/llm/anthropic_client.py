from __future__ import annotations

from typing import Optional

from anthropic import Anthropic

from ..config import settings
from .base import VisionInput, VisionLLMClient, TextLLMClient


class AnthropicVision(VisionLLMClient):
    def __init__(self) -> None:
        self.client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.AGENT_VISION_MODEL
        self.max_output_tokens = settings.AGENT_VISION_MODEL_MAX_OUTPUT_TOKENS

    def generate(self, req: VisionInput, *, max_tokens: Optional[int] = None) -> str:
        from base64 import b64encode

        try:
            b64 = b64encode(req.image_bytes).decode("utf-8")
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens or self.max_output_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": req.instructions},
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": b64,
                                },
                            },
                        ],
                    }
                ],
            )
            return resp.content[0].text if resp.content else ""
        except Exception:
            return ""


class AnthropicText(TextLLMClient):
    def __init__(self) -> None:
        self.client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.TEXT_AI_MODEL
        self.max_output_tokens = settings.TEXT_AI_MODEL_MAX_OUTPUT_TOKENS

    def generate(self, prompt: str, *, max_tokens: Optional[int] = None) -> str:
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens or self.max_output_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text if resp.content else ""
        except Exception:
            return ""


__all__ = ["AnthropicVision", "AnthropicText"]
