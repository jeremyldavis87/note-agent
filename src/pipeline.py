from __future__ import annotations

import concurrent.futures as cf
import json
from pathlib import Path
from typing import Dict, List, Tuple

import cv2

from .config import settings
from .logging_setup import setup_logging
from .schema import Document, ImageMetadata, Note, Summary
from .llm.factory import get_clients
from .llm.base import VisionInput
from .image_ops.preprocess import preprocess_image
from .image_ops.color import dominant_color, describe_background_color
from .image_ops.qr import detect_qr_positions
from .detect.multinote import detect_regions
from .prompts import VISION_EXTRACTION_PROMPT, TEXT_ENRICH_PROMPT


def _normalize_bullets(text: str) -> str:
    return text.replace("- ", "• ")


def _count_checkboxes(text: str) -> int:
    return text.count("☐") + text.count("☑")


def process_image(image_path: Path, *, force_single: bool = False) -> Document:
    setup_logging()
    bgr = cv2.imread(str(image_path))
    if bgr is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")

    pre = preprocess_image(bgr)

    # Color/background
    b, g, r = dominant_color(bgr)
    bg_label = describe_background_color((r, g, b))

    # Regions
    regions = detect_regions(pre.image, force_single)

    # Providers
    vision_client, text_client = get_clients()

    notes: List[Note] = []

    def process_region(idx: int):
        region = regions[idx]
        x, y, w, h = region.bbox
        crop = bgr[y : y + h, x : x + w]
        _, jpeg = cv2.imencode(".jpg", crop)
        content = vision_client.generate(
            VisionInput(image_bytes=jpeg.tobytes(), instructions=VISION_EXTRACTION_PROMPT),
            max_tokens=settings.AGENT_VISION_MODEL_MAX_OUTPUT_TOKENS,
        )
        # Ask model to reply with plain text; here we treat the entire reply as raw text
        raw_text = content.strip()
        formatted = _normalize_bullets(raw_text)
        enrich_json = text_client.generate(
            f"Input note text:\n\n{raw_text}\n\n{TEXT_ENRICH_PROMPT}",
            max_tokens=settings.TEXT_AI_MODEL_MAX_OUTPUT_TOKENS,
        )
        try:
            enrich = json.loads(enrich_json)
        except Exception:
            enrich = {"action_items": [], "tags": []}

        note = Note(
            position=region.position_label,
            note_color=None,
            qr_code_present=None,
            qr_code_position=None,
            title=None,
            header=None,
            raw_text=raw_text,
            formatted_text=formatted,
            action_items=list(enrich.get("action_items", [])),
            tags=list(enrich.get("tags", [])),
            checkboxes=_count_checkboxes(raw_text) or None,
            confidence_score=0.9,
            processing_method="vision_llm",
        )
        return note

    with cf.ThreadPoolExecutor(max_workers=settings.AGENT_PARALLEL_PROCESSING_LIMIT) as pool:
        for note in pool.map(process_region, range(len(regions))):
            notes.append(note)

    # QR detection (for overall metadata)
    qr = detect_qr_positions(bgr)
    all_qr_present = len(qr) >= len(notes)

    # Summary
    total_actions = sum(len(n.action_items) for n in notes)
    colors_used = [c for c in {n.note_color for n in notes if n.note_color}]

    doc = Document(
        image_metadata=ImageMetadata(
            total_notes_detected=len(notes),
            detection_method="grid_heuristic" if not force_single else "single_note",
            background_color=bg_label,
            note_arrangement="3x3_grid" if not force_single else None,
        ),
        notes=notes,
        summary=Summary(
            total_action_items=total_actions,
            main_themes=[],
            note_colors_used=colors_used or ["orange", "green", "blue"],
            all_qr_codes_present=all_qr_present,
            notebook_brand="Rocketbook",
        ),
    )

    return doc


def run_to_file(image_path: str, out_path: str, *, force_single: bool = False) -> None:
    doc = process_image(Path(image_path), force_single=force_single)
    Path(out_path).write_text(doc.model_dump_json(indent=2))


__all__ = ["process_image", "run_to_file"]
