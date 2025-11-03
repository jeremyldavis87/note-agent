from __future__ import annotations

import concurrent.futures as cf
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import cv2

from .config import settings
from .logging_setup import setup_logging
from .schema import Document, ImageMetadata, Note, Summary
from .llm.factory import get_clients
from .llm.base import VisionInput
from .image_ops.preprocess import preprocess_image
from .image_ops.color import dominant_color, describe_background_color, validate_note_color
from .image_ops.qr import detect_qr_positions, detect_qr_in_region, get_qr_code_info
from .detect.multinote import detect_regions
from .prompts import build_vision_prompt, build_text_enrich_prompt
from .judge import judge_extraction
from .context import (
    load_abbreviations_dict,
    extract_relevant_abbreviations,
    format_abbreviations_context,
    load_org_hierarchy,
    build_people_index,
    extract_org_context_from_text,
    format_org_context,
    load_personal_context,
    extract_relevant_context_for_text,
    format_personal_context,
)


def _normalize_bullets(text: str) -> str:
    return text.replace("- ", "• ")


def _count_checkboxes(text: str) -> int:
    return text.count("☐") + text.count("☑")


def _extract_title(text: str) -> Optional[str]:
    """
    Extract title from text using regex pattern for double-hash titles.
    
    Matches patterns like ##Title## and extracts the title text.
    Returns None if no match found.
    
    Args:
        text: The raw text to search for double-hash titles
        
    Returns:
        Extracted title string without the hashes, or None if not found
    """
    pattern = r"##([^#]+)##"
    match = re.search(pattern, text)
    if match:
        title = match.group(1).strip()
        return title if title else None
    return None


def _parse_vision_response(
    content: str,
) -> Tuple[str, Optional[str], Optional[bool], Optional[str]]:
    """
    Parse vision LLM response to extract text and metadata.
    
    Handles both structured JSON responses (new format) and plain text (backward compatibility).
    
    Args:
        content: Raw response from vision LLM
        
    Returns:
        Tuple of (raw_text, note_color, qr_code_present, qr_code_position)
        - raw_text: Extracted text content (always present)
        - note_color: Color name or None
        - qr_code_present: Boolean or None
        - qr_code_position: Position string or None
    """
    content = content.strip()
    
    # Try to parse as JSON first
    try:
        json_str = content.strip()
        data = None
        
        # First, try to extract JSON from markdown code blocks
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", json_str, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
            data = json.loads(json_str)
        else:
            # Try parsing entire response as JSON
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError:
                # If that fails, try to find JSON object by finding matching braces
                start_idx = json_str.find("{")
                if start_idx >= 0:
                    # Find matching closing brace by counting braces
                    brace_count = 0
                    end_idx = start_idx
                    for i in range(start_idx, len(json_str)):
                        if json_str[i] == "{":
                            brace_count += 1
                        elif json_str[i] == "}":
                            brace_count -= 1
                            if brace_count == 0:
                                end_idx = i + 1
                                break
                    if end_idx > start_idx:
                        json_str = json_str[start_idx:end_idx]
                        data = json.loads(json_str)
        
        # If we have data, extract fields
        if data:
            raw_text = data.get("text", content)  # Fallback to full content if no text field
            note_color = data.get("note_color")
            if note_color == "null" or note_color == "":
                note_color = None
            
            qr_code_present = data.get("qr_code_present")
            if isinstance(qr_code_present, str):
                qr_code_present = qr_code_present.lower() in ("true", "1", "yes")
            elif qr_code_present is None:
                qr_code_present = None
            
            qr_code_position = data.get("qr_code_position")
            if qr_code_position == "null" or qr_code_position == "":
                qr_code_position = None
            
            return (raw_text, note_color, qr_code_present, qr_code_position)
        else:
            # Couldn't parse as JSON - treat as plain text (backward compatibility)
            return (content, None, None, None)
        
    except (json.JSONDecodeError, KeyError, AttributeError, ValueError):
        # Not valid JSON or missing fields - treat as plain text (backward compatibility)
        return (content, None, None, None)


def process_image(image_path: Path, *, force_single: bool = False) -> Document:
    # Setup logging with file handler if log directory is available
    # Force a new log directory for each image processing run
    from .telemetry import get_log_directory
    log_dir = get_log_directory(force_new=True)
    setup_logging(log_dir=log_dir)
    
    import logging
    logger = logging.getLogger(__name__)
    logger.debug(f"Starting image processing: {image_path}")
    logger.debug(f"Force single mode: {force_single}")
    
    import time
    total_start = time.time()
    
    bgr = cv2.imread(str(image_path))
    if bgr is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")
    logger.debug(f"Image loaded: shape={bgr.shape}, dtype={bgr.dtype}")

    pre_start = time.time()
    pre = preprocess_image(bgr)
    pre_duration = time.time() - pre_start
    logger.debug(f"Image preprocessing completed in {pre_duration:.3f}s")

    # Color/background
    color_start = time.time()
    b, g, r = dominant_color(bgr)
    bg_label = describe_background_color((r, g, b))
    color_duration = time.time() - color_start
    logger.debug(f"Color analysis completed in {color_duration:.3f}s: dominant_color=({r},{g},{b}), label={bg_label}")

    # Regions
    region_start = time.time()
    regions = detect_regions(pre.image, force_single)
    region_duration = time.time() - region_start
    logger.debug(f"Region detection completed in {region_duration:.3f}s: found {len(regions)} regions")

    # Providers
    client_start = time.time()
    vision_client, text_client = get_clients()
    client_duration = time.time() - client_start
    logger.debug(f"LLM clients initialized in {client_duration:.3f}s")

    # Load all context files once for this image processing session
    context_start = time.time()
    abbreviations_dict = load_abbreviations_dict()
    logger.debug(f"Loaded {len(abbreviations_dict)} abbreviations")
    
    org_hierarchy = load_org_hierarchy()
    logger.debug(f"Loaded org hierarchy: {bool(org_hierarchy)}")
    
    personal_context = load_personal_context()
    logger.debug(f"Loaded personal context: {bool(personal_context)}")
    
    # Build people index from org hierarchy for efficient searching
    people_index = None
    if org_hierarchy:
        index_start = time.time()
        people_index = build_people_index(org_hierarchy)
        index_duration = time.time() - index_start
        all_people = people_index.get("all_people", [])
        logger.debug(f"Built people index in {index_duration:.3f}s: {len(all_people)} people indexed")
    
    context_duration = time.time() - context_start
    logger.debug(f"Total context loading time: {context_duration:.3f}s")
    
    # Prepare general context for vision prompt (common abbreviations and org terms)
    # For vision phase, we include common abbreviations since we don't have text yet
    common_abbreviations_context = ""
    if abbreviations_dict:
        # Format all abbreviations for vision prompt to help with OCR recognition
        common_abbreviations_context = format_abbreviations_context(abbreviations_dict)
    
    # Build vision prompt with context
    vision_prompt = build_vision_prompt(
        abbreviations_context=common_abbreviations_context,
        org_context=""  # Org context will be extracted after text extraction
    )

    notes: List[Note] = []
    
    # QR detection on full image (for mapping to regions)
    # Try preprocessed image first (better for QR detection - grayscale, denoised, contrast-stretched)
    qr_mapping_start = time.time()
    # Convert preprocessed grayscale to BGR format for detect_qr_positions (which expects BGR)
    if len(pre.image.shape) == 2:
        # Grayscale to BGR
        pre_bgr = cv2.cvtColor(pre.image, cv2.COLOR_GRAY2BGR)
    else:
        pre_bgr = pre.image
    
    qr_full = detect_qr_positions(pre_bgr)
    if not qr_full:
        # Fallback to original if preprocessed didn't find any
        qr_full = detect_qr_positions(bgr)
    
    # Map QR codes to regions for individual note QR info
    qr_to_region_map = {}
    if qr_full:
        for qr_data, (qr_x, qr_y, qr_w, qr_h) in qr_full:
            qr_center_x = qr_x + qr_w // 2
            qr_center_y = qr_y + qr_h // 2
            # Find which region this QR code belongs to
            for idx_map, region in enumerate(regions):
                rx, ry, rw, rh = region.bbox
                if rx <= qr_center_x < rx + rw and ry <= qr_center_y < ry + rh:
                    qr_to_region_map[idx_map] = qr_data
                    break
        logger.debug(f"Full image QR detection: found {len(qr_full)} QR codes, mapped {len(qr_to_region_map)} to regions")
    qr_mapping_duration = time.time() - qr_mapping_start
    logger.debug(f"QR mapping completed in {qr_mapping_duration:.3f}s")

    def process_region(idx: int):
        import logging
        import time
        logger = logging.getLogger(__name__)
        start_time = time.time()
        
        region = regions[idx]
        x, y, w, h = region.bbox
        logger.debug(f"Processing region {idx}: position={region.position_label}, bbox=({x},{y},{w},{h})")
        
        crop = bgr[y : y + h, x : x + w]
        # Also get preprocessed crop for QR detection (better for QR: grayscale, denoised, contrast-stretched)
        pre_crop = pre.image[y : y + h, x : x + w]
        # Convert preprocessed grayscale to BGR format for detect_qr_in_region
        if len(pre_crop.shape) == 2:
            # Grayscale to BGR for consistency
            pre_crop_bgr = cv2.cvtColor(pre_crop, cv2.COLOR_GRAY2BGR)
        else:
            pre_crop_bgr = pre_crop
        
        _, jpeg = cv2.imencode(".jpg", crop)
        jpeg_size = len(jpeg.tobytes())
        logger.debug(f"Region {idx}: encoded JPEG size={jpeg_size} bytes")
        
        vision_start = time.time()
        content = vision_client.generate(
            VisionInput(image_bytes=jpeg.tobytes(), instructions=vision_prompt),
            max_tokens=settings.AGENT_VISION_MODEL_MAX_OUTPUT_TOKENS,
        )
        vision_duration = time.time() - vision_start
        logger.debug(f"Region {idx}: vision extraction completed in {vision_duration:.3f}s, output length={len(content)}")
        
        # Parse vision response for text and metadata
        raw_text, llm_note_color, llm_qr_present, llm_qr_position = _parse_vision_response(content)
        formatted = _normalize_bullets(raw_text)
        logger.debug(f"Region {idx}: extracted text length={len(raw_text)}, formatted length={len(formatted)}")
        
        # Programmatic QR detection - use preprocessed version (better for QR detection)
        qr_start = time.time()
        qr_result = detect_qr_in_region(pre_crop_bgr)
        qr_duration = time.time() - qr_start
        prog_qr_present = qr_result is not None
        prog_qr_position = qr_result[0] if qr_result else None
        prog_qr_info = qr_result[1] if (qr_result and len(qr_result) > 1 and qr_result[1]) else None
        
        # Also check if we mapped a QR code from full image detection
        full_image_qr_info = qr_to_region_map.get(idx)
        
        logger.debug(f"Region {idx}: programmatic QR detection completed in {qr_duration:.3f}s: present={prog_qr_present}, position={prog_qr_position}, info_length={len(prog_qr_info) if prog_qr_info else 0}, full_image_mapped={bool(full_image_qr_info)}")
        
        # Combine LLM and programmatic QR detection (prefer programmatic for presence, LLM for position)
        qr_code_info = None
        if prog_qr_present:
            qr_code_present = True
            # Prefer programmatic position, but use LLM position if programmatic didn't provide one
            qr_code_position = prog_qr_position or llm_qr_position
            # Use programmatic QR info (decoded data)
            qr_code_info = prog_qr_info if prog_qr_info else None
        elif full_image_qr_info:
            # Use QR code mapped from full image detection
            qr_code_present = True
            qr_code_position = llm_qr_position or "bottom_right"  # Default to bottom_right if LLM didn't specify
            qr_code_info = full_image_qr_info
        elif llm_qr_present is True:
            # Trust LLM if programmatic didn't find one but LLM says it's present
            qr_code_present = True
            qr_code_position = llm_qr_position
            # Try to get QR info using get_qr_code_info as fallback (use preprocessed)
            qr_code_info = get_qr_code_info(pre_crop_bgr)
        else:
            # Neither found it, or LLM says False
            qr_code_present = False if llm_qr_present is False else None
            qr_code_position = None
            qr_code_info = None
        logger.debug(f"Region {idx}: combined QR detection: present={qr_code_present}, position={qr_code_position}, info={'present' if qr_code_info else 'none'}")
        
        # Color validation (optional - LLM is primary)
        note_color = llm_note_color
        if note_color:
            validated_color = validate_note_color(crop, note_color)
            if validated_color and validated_color != note_color.lower():
                logger.debug(f"Region {idx}: color validation adjusted from '{note_color}' to '{validated_color}'")
                note_color = validated_color
            elif validated_color:
                logger.debug(f"Region {idx}: color '{note_color}' validated successfully")
            elif note_color.lower() in {"orange", "green", "blue", "yellow", "pink", "purple", "red"}:
                # LLM suggested a valid color but validation didn't confirm - trust LLM
                note_color = note_color.lower()
                logger.debug(f"Region {idx}: using LLM-suggested color '{note_color}' (validation inconclusive)")
            else:
                # Invalid color suggestion - set to None
                logger.debug(f"Region {idx}: invalid color suggestion '{note_color}', setting to None")
                note_color = None
        else:
            logger.debug(f"Region {idx}: no color detected by LLM")
        
        # Extract relevant context from raw_text
        # Abbreviations
        abbrev_start = time.time()
        relevant_abbreviations = extract_relevant_abbreviations(raw_text, abbreviations_dict)
        abbreviations_context = format_abbreviations_context(relevant_abbreviations)
        abbrev_duration = time.time() - abbrev_start
        logger.debug(f"Region {idx}: found {len(relevant_abbreviations)} abbreviations in {abbrev_duration:.3f}s")
        if relevant_abbreviations:
            logger.debug(f"Region {idx}: abbreviations={list(relevant_abbreviations.keys())}")
        
        # Organizational context (people mentioned, etc.)
        org_context_dict = {}
        org_context_str = ""
        if org_hierarchy and people_index:
            org_start = time.time()
            org_context_dict = extract_org_context_from_text(
                raw_text,
                hierarchy=org_hierarchy,
                people_index=people_index
            )
            org_context_str = format_org_context(org_context_dict)
            org_duration = time.time() - org_start
            people_count = len(org_context_dict.get("people_mentioned", []))
            logger.debug(f"Region {idx}: found {people_count} people in org context in {org_duration:.3f}s")
            if people_count > 0:
                logger.debug(f"Region {idx}: people mentioned={[p.get('name') for p in org_context_dict.get('people_mentioned', [])]}")
        
        # Personal/professional context
        personal_context_str = ""
        if personal_context:
            personal_start = time.time()
            relevant_personal_context = extract_relevant_context_for_text(
                raw_text,
                personal_context=personal_context
            )
            personal_context_str = format_personal_context(relevant_personal_context)
            personal_duration = time.time() - personal_start
            logger.debug(f"Region {idx}: extracted personal context in {personal_duration:.3f}s")
        
        # Build enrichment prompt with all context
        enrich_prompt = build_text_enrich_prompt(
            abbreviations_context=abbreviations_context,
            org_context=org_context_str,
            personal_context=personal_context_str
        )
        logger.debug(f"Region {idx}: enrichment prompt length={len(enrich_prompt)}")
        
        enrich_start = time.time()
        enrich_json = text_client.generate(
            f"Input note text:\n\n{raw_text}\n\n{enrich_prompt}",
            max_tokens=settings.TEXT_AI_MODEL_MAX_OUTPUT_TOKENS,
        )
        enrich_duration = time.time() - enrich_start
        logger.debug(f"Region {idx}: text enrichment completed in {enrich_duration:.3f}s, output length={len(enrich_json)}")
        try:
            enrich = json.loads(enrich_json)
            logger.debug(f"Region {idx}: parsed enrichment, action_items={len(enrich.get('action_items', []))}, tags={len(enrich.get('tags', []))}")
        except Exception as e:
            logger.warning(f"Region {idx}: failed to parse enrichment JSON: {e}")
            enrich = {"action_items": [], "tags": [], "title": None}
        
        # Extract title: prefer LLM-extracted title, fallback to regex for double-hash titles
        title = enrich.get("title")
        # Normalize title: trim whitespace and handle string "null"
        if title:
            title = str(title).strip() if title != "null" else None
            if not title:  # Empty string after strip
                title = None
        
        # Fallback to regex extraction for double-hash titles if LLM didn't provide one
        if not title:
            title = _extract_title(raw_text)
            if title:
                logger.debug(f"Region {idx}: extracted title via regex: {title}")
        
        if title:
            logger.debug(f"Region {idx}: title={title}")

        note = Note(
            position=region.position_label,
            note_color=note_color,
            qr_code_present=qr_code_present,
            qr_code_position=qr_code_position,
            qr_code_info=qr_code_info if qr_code_info else None,
            title=title,
            header=None,
            raw_text=raw_text,
            formatted_text=formatted,
            action_items=list(enrich.get("action_items", [])),
            tags=list(enrich.get("tags", [])),
            checkboxes=_count_checkboxes(raw_text) or None,
            confidence_score=0.9,
            processing_method="vision_llm",
        )
        
        total_duration = time.time() - start_time
        logger.debug(f"Region {idx}: total processing time={total_duration:.3f}s")
        return note

    processing_start = time.time()
    logger.debug(f"Starting parallel processing of {len(regions)} regions with max_workers={settings.AGENT_PARALLEL_PROCESSING_LIMIT}")
    with cf.ThreadPoolExecutor(max_workers=settings.AGENT_PARALLEL_PROCESSING_LIMIT) as pool:
        for note in pool.map(process_region, range(len(regions))):
            notes.append(note)
    processing_duration = time.time() - processing_start
    logger.debug(f"All regions processed in {processing_duration:.3f}s (parallel)")

    # QR detection (for overall metadata) - reuse results from mapping
    all_qr_present = len(qr_full) >= len(notes)
    logger.debug(f"QR detection summary: found {len(qr_full)} QR codes, all_present={all_qr_present}")

    # Summary
    summary_start = time.time()
    total_actions = sum(len(n.action_items) for n in notes)
    colors_used = [c for c in {n.note_color for n in notes if n.note_color}]
    summary_duration = time.time() - summary_start
    logger.debug(f"Summary generation completed in {summary_duration:.3f}s: total_actions={total_actions}, colors={colors_used}")

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
    
    total_duration = time.time() - total_start
    logger.debug(f"Total image processing time: {total_duration:.3f}s")
    logger.info(f"Processed {len(notes)} notes in {total_duration:.2f}s")

    # Optional: Run judge evaluation
    if settings.AGENT_ENABLE_JUDGE:
        try:
            import logging
            logger = logging.getLogger(__name__)
            logger.info("Running judge evaluation")
            judge_result = judge_extraction(image_path, doc)
            logger.info(f"Judge overall score: {judge_result.get('overall_score', 'N/A')}")
            if judge_result.get("issues_found"):
                logger.info(f"Judge found {len(judge_result['issues_found'])} issues")
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Judge evaluation failed: {e}")

    return doc


def run_to_file(image_path: str, out_path: str, *, force_single: bool = False) -> None:
    doc = process_image(Path(image_path), force_single=force_single)
    Path(out_path).write_text(doc.model_dump_json(indent=2))


def process_multiple_images(image_paths: List[str], out_path: str, *, force_single: bool = False) -> None:
    """
    Process multiple images and aggregate all notes into a single JSON output.
    
    Args:
        image_paths: List of image file paths to process
        out_path: Path to write the aggregated JSON output
        force_single: Force single note mode for all images
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Processing {len(image_paths)} images for aggregation")
    
    all_docs = []
    all_notes = []
    
    # Process each image
    for idx, image_path in enumerate(image_paths):
        logger.info(f"Processing image {idx + 1}/{len(image_paths)}: {image_path}")
        doc = process_image(Path(image_path), force_single=force_single)
        all_docs.append(doc)
        all_notes.extend(doc.notes)
        logger.debug(f"Image {idx + 1}: extracted {len(doc.notes)} notes")
    
    # Aggregate metadata
    total_notes_detected = sum(doc.image_metadata.total_notes_detected for doc in all_docs)
    
    # Combine detection methods (use "multiple_images" if different methods, otherwise keep method)
    detection_methods = {doc.image_metadata.detection_method for doc in all_docs}
    if len(detection_methods) == 1:
        detection_method = all_docs[0].image_metadata.detection_method
    else:
        detection_method = "multiple_images"
    
    # Combine background colors (use first, or "mixed" if different)
    background_colors = {doc.image_metadata.background_color for doc in all_docs if doc.image_metadata.background_color}
    if len(background_colors) == 1:
        background_color = all_docs[0].image_metadata.background_color
    elif len(background_colors) > 1:
        background_color = "mixed"
    else:
        background_color = None
    
    # Combine note arrangements (use "multiple_images" if different arrangements)
    note_arrangements = {doc.image_metadata.note_arrangement for doc in all_docs if doc.image_metadata.note_arrangement}
    if len(note_arrangements) == 1 and note_arrangements:
        note_arrangement = all_docs[0].image_metadata.note_arrangement
    elif len(note_arrangements) > 1:
        note_arrangement = "multiple_images"
    else:
        note_arrangement = None
    
    # Aggregate summary
    total_action_items = sum(doc.summary.total_action_items for doc in all_docs)
    
    # Combine and deduplicate themes
    all_themes = []
    for doc in all_docs:
        all_themes.extend(doc.summary.main_themes)
    main_themes = sorted(list(set(all_themes)))  # Deduplicate and sort
    
    # Combine and deduplicate note colors
    all_colors = []
    for doc in all_docs:
        all_colors.extend(doc.summary.note_colors_used)
    note_colors_used = sorted(list(set(all_colors)))  # Deduplicate and sort
    
    # All QR codes present only if all images have QR codes
    qr_values = [doc.summary.all_qr_codes_present for doc in all_docs if doc.summary.all_qr_codes_present is not None]
    if qr_values:
        all_qr_codes_present = all(qr_values)
    else:
        all_qr_codes_present = None
    
    # Notebook brand: use first non-None value, or None if all are None
    notebook_brand = next(
        (doc.summary.notebook_brand for doc in all_docs if doc.summary.notebook_brand),
        None
    )
    
    # Create aggregated document
    aggregated_doc = Document(
        image_metadata=ImageMetadata(
            total_notes_detected=total_notes_detected,
            detection_method=detection_method,
            background_color=background_color,
            note_arrangement=note_arrangement,
        ),
        notes=all_notes,
        summary=Summary(
            total_action_items=total_action_items,
            main_themes=main_themes,
            note_colors_used=note_colors_used if note_colors_used else ["orange", "green", "blue"],
            all_qr_codes_present=all_qr_codes_present,
            notebook_brand=notebook_brand,
        ),
    )
    
    # Write to output file
    Path(out_path).write_text(aggregated_doc.model_dump_json(indent=2))
    logger.info(f"Aggregated {total_notes_detected} notes from {len(image_paths)} images into {out_path}")


__all__ = ["process_image", "run_to_file", "process_multiple_images"]
