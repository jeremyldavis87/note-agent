from __future__ import annotations

from typing import Optional

from openai import OpenAI

from ..config import settings
from ..telemetry import wrap_openai_client, init_braintrust_logger
from .base import VisionInput, VisionLLMClient, TextLLMClient


class OpenAIVision(VisionLLMClient):
    def __init__(self) -> None:
        # Initialize Braintrust logger if enabled
        init_braintrust_logger()
        
        # Create OpenAI client and wrap with Braintrust for automatic tracing
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.client = wrap_openai_client(client)
        self.model = settings.AGENT_VISION_MODEL
        self.max_output_tokens = settings.AGENT_VISION_MODEL_MAX_OUTPUT_TOKENS

    def generate(self, req: VisionInput, *, max_tokens: Optional[int] = None) -> str:
        from base64 import b64encode

        try:
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
                max_completion_tokens=max_tokens or self.max_output_tokens,
            )
            return resp.choices[0].message.content or ""
        except Exception:
            return ""


class OpenAIText(TextLLMClient):
    def __init__(self) -> None:
        # Initialize Braintrust logger if enabled
        init_braintrust_logger()
        
        # Create OpenAI client and wrap with Braintrust for automatic tracing
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.client = wrap_openai_client(client)
        self.model = settings.TEXT_AI_MODEL
        self.max_output_tokens = settings.TEXT_AI_MODEL_MAX_OUTPUT_TOKENS

    def generate(self, prompt: str, *, max_tokens: Optional[int] = None) -> str:
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=max_tokens or self.max_output_tokens,
            )
            return resp.choices[0].message.content or ""
        except Exception:
            return ""


__all__ = ["OpenAIVision", "OpenAIText"]
