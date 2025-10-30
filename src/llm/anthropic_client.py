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

        b64 = b64encode(req.image_bytes).decode("utf-8")
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens or self.max_output_tokens,
            temperature=0.2,
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


class AnthropicText(TextLLMClient):
    def __init__(self) -> None:
        self.client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.TEXT_AI_MODEL
        self.max_output_tokens = settings.TEXT_AI_MODEL_MAX_OUTPUT_TOKENS

    def generate(self, prompt: str, *, max_tokens: Optional[int] = None) -> str:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens or self.max_output_tokens,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text if resp.content else ""


__all__ = ["AnthropicVision", "AnthropicText"]
