from __future__ import annotations

from typing import Optional

from openai import OpenAI

from ..config import settings
from .base import VisionInput, VisionLLMClient, TextLLMClient


class OpenAIVision(VisionLLMClient):
    def __init__(self) -> None:
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.AGENT_VISION_MODEL
        self.max_output_tokens = settings.AGENT_VISION_MODEL_MAX_OUTPUT_TOKENS

    def generate(self, req: VisionInput, *, max_tokens: Optional[int] = None) -> str:
        # Uses Chat Completions with image_url data URI
        from base64 import b64encode

        b64 = b64encode(req.image_bytes).decode("utf-8")
        image_url = f"data:image/jpeg;base64,{b64}"
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": req.instructions},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
            temperature=0.2,
            max_tokens=max_tokens or self.max_output_tokens,
        )
        return resp.choices[0].message.content or ""


class OpenAIText(TextLLMClient):
    def __init__(self) -> None:
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.TEXT_AI_MODEL
        self.max_output_tokens = settings.TEXT_AI_MODEL_MAX_OUTPUT_TOKENS

    def generate(self, prompt: str, *, max_tokens: Optional[int] = None) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=max_tokens or self.max_output_tokens,
        )
        return resp.choices[0].message.content or ""


__all__ = ["OpenAIVision", "OpenAIText"]
