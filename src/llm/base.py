from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Protocol


@dataclass
class VisionInput:
    image_bytes: bytes
    instructions: str


class VisionLLMClient(Protocol):
    def generate(self, req: VisionInput, *, max_tokens: Optional[int] = None) -> str: ...


class TextLLMClient(Protocol):
    def generate(self, prompt: str, *, max_tokens: Optional[int] = None) -> str: ...


__all__ = ["VisionInput", "VisionLLMClient", "TextLLMClient"]
