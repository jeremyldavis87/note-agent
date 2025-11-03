from __future__ import annotations

from typing import List, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


class ImageMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_notes_detected: int
    detection_method: Literal["visual_analysis", "qr_grid", "grid_heuristic", "single_note", "multiple_images"]
    background_color: Optional[str] = None
    note_arrangement: Optional[str] = None


class Note(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: Optional[str] = None
    note_color: Optional[str] = None
    qr_code_present: Optional[bool] = None
    qr_code_position: Optional[str] = None
    qr_code_info: Optional[str] = None

    title: Optional[str] = None
    header: Optional[str] = None
    raw_text: str
    formatted_text: str
    action_items: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    checkboxes: Optional[int] = None
    confidence_score: float
    processing_method: Literal["vision_llm", "ocr_llm", "ocr_tesseract"]


class Summary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_action_items: int
    main_themes: List[str]
    note_colors_used: List[str]
    all_qr_codes_present: Optional[bool] = None
    notebook_brand: Optional[str] = None


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_metadata: ImageMetadata
    notes: List[Note]
    summary: Summary


__all__ = [
    "ImageMetadata",
    "Note",
    "Summary",
    "Document",
]
