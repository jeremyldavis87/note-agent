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


def _calculate_spatial_proximity(pos1: str, pos2: str) -> int:
    """
    Calculate spatial proximity between two grid positions.
    Returns a lower number for closer positions (same row/adjacent cells).
    
    Args:
        pos1: Position string like "row_1_col_1"
        pos2: Position string like "row_1_col_2"
        
    Returns:
        Proximity score (lower = closer)
    """
    if not pos1 or not pos2:
        return 999
    
    try:
        # Extract row and column numbers
        row1_match = re.search(r"row_(\d+)", pos1)
        col1_match = re.search(r"col_(\d+)", pos1)
        row2_match = re.search(r"row_(\d+)", pos2)
        col2_match = re.search(r"col_(\d+)", pos2)
        
        if not all([row1_match, col1_match, row2_match, col2_match]):
            return 999
        
        row1, col1 = int(row1_match.group(1)), int(col1_match.group(1))
        row2, col2 = int(row2_match.group(1)), int(col2_match.group(1))
        
        # Calculate Manhattan distance
        row_diff = abs(row1 - row2)
        col_diff = abs(col1 - col2)
        return row_diff * 3 + col_diff  # Weight rows more heavily
    except (ValueError, AttributeError):
        return 999


def _extract_semantic_keywords(text: str) -> set:
    """
    Extract semantic keywords and concepts from text to help identify related content.
    
    Args:
        text: Text to analyze
        
    Returns:
        Set of semantic keywords/concepts
    """
    keywords = set()
    text_lower = text.lower()
    
    # Extract person names (capitalized words that might be names)
    # Simple heuristic: words that are capitalized and appear standalone
    words = text.split()
    for word in words:
        if word and word[0].isupper() and len(word) > 2:
            # Filter out common non-name words
            if word.lower() not in ['the', 'and', 'with', 'from', 'that', 'this', 'have', 'been', 'will']:
                keywords.add(word.lower())
    
    # Extract technical terms (words with special patterns)
    tech_patterns = [
        r'\b[A-Z]{2,}\b',  # Acronyms like PII, PHI, API, etc.
        r'\b[a-z]+-[a-z]+\b',  # Hyphenated terms like de-identify
    ]
    for pattern in tech_patterns:
        matches = re.findall(pattern, text)
        keywords.update(m.lower() for m in matches)
    
    # Extract key concepts (common business/technical terms)
    concept_patterns = [
        r'\b(privacy|security|data|protection|identify|identify|compliance)\b',
        r'\b(meeting|1-on-1|discussion|review|follow)\b',
        r'\b(research|proposal|project|priority|initiative)\b',
    ]
    for pattern in concept_patterns:
        matches = re.findall(pattern, text_lower)
        keywords.update(matches)
    
    return keywords


def _combine_text_with_context(notes: List[Note]) -> str:
    """
    Combine text from multiple notes while preserving spatial and semantic context.
    
    This helps the LLM understand which content fragments belong together by:
    1. Grouping notes by spatial proximity (adjacent cells first)
    2. Adding semantic markers for related concepts
    3. Preserving note boundaries with subtle markers
    
    Args:
        notes: List of Note objects to combine
        
    Returns:
        Combined text with context markers
    """
    if not notes:
        return ""
    
    # Sort notes by spatial position to maintain grid order
    def position_key(note: Note) -> Tuple[int, int]:
        if not note.position:
            return (999, 999)
        row_match = re.search(r"row_(\d+)", note.position)
        col_match = re.search(r"col_(\d+)", note.position)
        row = int(row_match.group(1)) if row_match else 999
        col = int(col_match.group(1)) if col_match else 999
        return (row, col)
    
    sorted_notes = sorted(notes, key=position_key)
    
    # Extract semantic keywords from all notes to find relationships
    all_keywords = {}
    for note in sorted_notes:
        if note.raw_text:
            keywords = _extract_semantic_keywords(note.raw_text)
            for keyword in keywords:
                if keyword not in all_keywords:
                    all_keywords[keyword] = []
                all_keywords[keyword].append(note.position)
    
    # Find related notes (notes that share semantic keywords and are spatially close)
    related_groups = {}
    for keyword, positions in all_keywords.items():
        if len(positions) > 1:
            # Group positions by proximity
            for i, pos1 in enumerate(positions):
                for pos2 in positions[i+1:]:
                    proximity = _calculate_spatial_proximity(pos1, pos2)
                    if proximity <= 2:  # Same row or adjacent
                        group_key = tuple(sorted([pos1, pos2]))
                        if group_key not in related_groups:
                            related_groups[group_key] = set()
                        related_groups[group_key].add(keyword)
    
    # Combine text with context
    combined_parts = []
    for i, note in enumerate(sorted_notes):
        if not note.raw_text:
            continue
        
        text = note.raw_text
        
        # Add subtle proximity markers for nearby related content
        if i > 0:
            prev_note = sorted_notes[i-1]
            if prev_note.position and note.position:
                proximity = _calculate_spatial_proximity(prev_note.position, note.position)
                if proximity <= 1:
                    # Same row, adjacent columns - very likely related
                    pass  # No marker needed, just keep close
                elif proximity <= 3:
                    # Same row or adjacent row - possibly related
                    # Add a subtle separator that doesn't break semantic flow
                    combined_parts.append("\n")
        
        combined_parts.append(text)
    
    return "\n\n".join(combined_parts)


def _build_section_parsing_prompt() -> str:
    """
    Build a dynamic section parsing prompt that emphasizes semantic coherence
    without hardcoded rules.
    """
    return """Analyze the following note text and extract logical sections. The text may be fragmented across multiple regions, so you need to merge related content intelligently.

Sections are typically identified by:
- Clear section headers/names (person names, project names, topic headings)
- Separator lines (like "~", "~~~~~", "---", or horizontal lines)
- Major topic shifts

CRITICAL: Understand semantic coherence and spatial relationships:
1. **Semantic Coherence**: Content that discusses the same topic, person, project, or concept should be grouped together, even if fragmented across different regions. Look for:
   - Repeated names, keywords, or concepts
   - Related technical terms (e.g., "PII" and "de-identify" are privacy-related)
   - Related actions or discussions about the same subject
   - Contextual clues that indicate content belongs together

2. **Spatial Proximity**: Content from adjacent or nearby regions in the grid is more likely to be related than content from distant regions. However, semantic coherence should take precedence over spatial proximity when they conflict.

3. **Conceptual Relationships**: Understand relationships between concepts:
   - Related technical terms (e.g., privacy, security, data protection, PII, PHI, de-identification)
   - Related people (e.g., mentions of the same person with different formats)
   - Related projects or initiatives
   - Related actions or discussions

4. **Fragment Merging**: When you see fragmented text that clearly belongs to the same section (based on semantic coherence), merge it into a single section. Do NOT create separate sections for partial text fragments that are clearly part of a larger discussion.

For each section, identify:
1. The section title (the clear header/name, or null if no clear title exists)
2. The complete raw text content of that section (merge fragments if needed)
3. Action items extracted from that section
4. Tags relevant to that section
5. Number of checkboxes in that section

Return ONLY a valid JSON array of sections, each with:
{
  "section_title": "string or null",
  "raw_text": "string (complete merged text for this section, including all related fragments)",
  "action_items": ["array of strings"],
  "tags": ["array of strings"],
  "checkboxes": number
}

IMPORTANT: Return ONLY valid JSON. Do not include any markdown formatting, explanations, or additional text. Start your response with [ and end with ]. The response must be parseable as JSON.

Be conservative - only create separate sections when there are clear, distinct topics with clear headers. Merge fragments that clearly belong together based on semantic coherence. Prefer creating fewer, more complete sections rather than many fragmented ones."""


def _parse_sections_from_text(text: str, text_client) -> List[dict]:
    """
    Parse sections from combined text using LLM with dynamic semantic understanding.
    
    Args:
        text: Combined text from multiple notes
        text_client: LLM client for text generation
        
    Returns:
        List of section dictionaries
    """
    import logging
    logger = logging.getLogger(__name__)
    
    section_prompt = _build_section_parsing_prompt()
    
    try:
        response = text_client.generate(
            f"{section_prompt}\n\nText to parse:\n\n{text}",
            max_tokens=settings.TEXT_AI_MODEL_MAX_OUTPUT_TOKENS * 3,
        )
        
        if not response or not response.strip():
            logger.warning("Empty response from LLM for section parsing")
            raise ValueError("Empty response")
        
        # Robust JSON extraction
        json_text = response.strip()
        # Try extracting from markdown code blocks
        json_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", json_text, re.DOTALL)
        if json_match:
            json_text = json_match.group(1).strip()
        else:
            # Try finding JSON array in text
            array_match = re.search(r"(\[.*\])", json_text, re.DOTALL)
            if array_match:
                json_text = array_match.group(1)
        
        # Clean up any remaining markdown
        json_text = json_text.strip()
        if json_text.startswith("```"):
            json_text = json_text[3:]
            if json_text.startswith("json"):
                json_text = json_text[4:]
            json_text = json_text.strip()
        if json_text.endswith("```"):
            json_text = json_text[:-3].strip()
        
        sections = json.loads(json_text)
        if isinstance(sections, list):
            return sections
        elif isinstance(sections, dict) and "sections" in sections:
            return sections["sections"]
        else:
            logger.warning("LLM did not return array of sections, treating as single section")
            return [{
                "section_title": None,
                "raw_text": text,
                "action_items": [],
                "tags": [],
                "checkboxes": _count_checkboxes(text)
            }]
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse JSON from section parsing response: {e}")
        logger.debug(f"Response was: {response[:500] if response else 'None'}")
        return [{
            "section_title": None,
            "raw_text": text,
            "action_items": [],
            "tags": [],
            "checkboxes": _count_checkboxes(text)
        }]
    except Exception as e:
        logger.warning(f"Failed to parse sections: {e}, treating as single section")
        return [{
            "section_title": None,
            "raw_text": text,
            "action_items": [],
            "tags": [],
            "checkboxes": _count_checkboxes(text)
        }]


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
                brace_start = json_str.find("{")
                if brace_start != -1:
                    brace_count = 0
                    brace_end = -1
                    for i in range(brace_start, len(json_str)):
                        if json_str[i] == "{":
                            brace_count += 1
                        elif json_str[i] == "}":
                            brace_count -= 1
                            if brace_count == 0:
                                brace_end = i + 1
                                break
                    if brace_end != -1:
                        json_str = json_str[brace_start:brace_end]
                        data = json.loads(json_str)
        
        if data and isinstance(data, dict):
            raw_text = data.get("text", "")
            note_color = data.get("note_color")
            qr_code_present = data.get("qr_code_present")
            qr_code_position = data.get("qr_code_position")
            
            # Validate note_color
            if note_color:
                note_color = validate_note_color(note_color)
            
            return raw_text, note_color, qr_code_present, qr_code_position
    except (json.JSONDecodeError, KeyError, AttributeError) as e:
        pass
    
    # Fallback: treat entire response as plain text
    return content, None, None, None


def process_image(image_path: Path, *, force_single: bool = False) -> Document:
    # Setup logging with file handler if log directory is available
    # Force a new log directory for each image processing run
    setup_logging()
    
    import logging
    import time
    logger = logging.getLogger(__name__)
    logger.debug(f"Starting image processing: {image_path}")
    logger.debug(f"Force single mode: {force_single}")
    
    total_start = time.time()
    
    # Load image
    image_start = time.time()
    bgr = cv2.imread(str(image_path))
    if bgr is None:
        raise ValueError(f"Failed to load image: {image_path}")
    logger.debug(f"Image loaded: shape={bgr.shape}, dtype={bgr.dtype}")
    image_duration = time.time() - image_start
    
    # Preprocess
    preprocess_start = time.time()
    pre = preprocess_image(bgr)
    preprocess_duration = time.time() - preprocess_start
    logger.debug(f"Image preprocessing completed in {preprocess_duration:.3f}s")
    
    # Color analysis
    color_start = time.time()
    dom_color = dominant_color(bgr)
    bg_label = describe_background_color(dom_color)
    color_duration = time.time() - color_start
    logger.debug(f"Color analysis completed in {color_duration:.3f}s: dominant_color={dom_color}, label={bg_label}")
    
    # Region detection
    region_start = time.time()
    regions = detect_regions(bgr, force_single=force_single)
    region_duration = time.time() - region_start
    logger.debug(f"Region detection completed in {region_duration:.3f}s: found {len(regions)} regions")
    
    # Get LLM clients
    vision_client, text_client = get_clients()
    
    # Load context
    context_start = time.time()
    abbreviations_dict = load_abbreviations_dict()
    logger.debug(f"Loaded abbreviations: {bool(abbreviations_dict)}")
    
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
            
            # Find the region that contains this QR code center
            for idx, region in enumerate(regions):
                rx, ry, rw, rh = region.bbox
                if (rx <= qr_center_x <= rx + rw and
                    ry <= qr_center_y <= ry + rh):
                    if idx not in qr_to_region_map:
                        qr_to_region_map[idx] = []
                    qr_to_region_map[idx].append((qr_data, (qr_x, qr_y, qr_w, qr_h)))
    
    qr_mapping_duration = time.time() - qr_mapping_start
    logger.debug(f"QR mapping completed in {qr_mapping_duration:.3f}s: mapped {len(qr_to_region_map)} regions with QR codes")
    
    def process_region(idx: int):
        start_time = time.time()
        region = regions[idx]
        x, y, w, h = region.bbox
        
        # Extract region image
        region_img = bgr[y:y+h, x:x+w]
        
        # Vision extraction
        vision_start = time.time()
        # Convert image to JPEG bytes
        _, img_bytes = cv2.imencode('.jpg', region_img)
        vision_input = VisionInput(image_bytes=img_bytes.tobytes(), instructions=vision_prompt)
        vision_response = vision_client.generate(vision_input)
        vision_duration = time.time() - vision_start
        logger.debug(f"Region {idx}: vision extraction completed in {vision_duration:.3f}s, response length={len(vision_response)}")
        
        # Parse vision response
        raw_text, note_color, llm_qr_present, llm_qr_position = _parse_vision_response(vision_response)
        
        # Format text
        formatted = _normalize_bullets(raw_text)
        
        # QR detection (programmatic)
        qr_start = time.time()
        prog_qr_present, prog_qr_position, prog_qr_info = detect_qr_in_region(region_img)
        
        # Also check if QR code from full image mapping is in this region
        full_image_qr_info = None
        if idx in qr_to_region_map:
            # Use the first QR code found in this region
            qr_data, qr_coords = qr_to_region_map[idx][0]
            full_image_qr_info = get_qr_code_info(qr_data)
            if not prog_qr_present:
                # Use full image QR detection if programmatic didn't find it
                prog_qr_present = True
                # Calculate position relative to region
                qr_x, qr_y, qr_w, qr_h = qr_coords
                region_center_x = w // 2
                region_center_y = h // 2
                qr_rel_x = qr_x - x
                qr_rel_y = qr_y - y
                qr_rel_center_x = qr_rel_x + qr_w // 2
                qr_rel_center_y = qr_rel_y + qr_h // 2
                
                if qr_rel_center_x < region_center_x and qr_rel_center_y > region_center_y:
                    prog_qr_position = "bottom_left"
                elif qr_rel_center_x >= region_center_x and qr_rel_center_y > region_center_y:
                    prog_qr_position = "bottom_right"
                elif qr_rel_center_x < region_center_x and qr_rel_center_y <= region_center_y:
                    prog_qr_position = "top_left"
                else:
                    prog_qr_position = "top_right"
        
        qr_code_present = prog_qr_present or llm_qr_present
        qr_code_position = prog_qr_position or llm_qr_position
        qr_code_info = full_image_qr_info or prog_qr_info
        
        qr_duration = time.time() - qr_start
        logger.debug(f"Region {idx}: programmatic QR detection completed in {qr_duration:.3f}s: present={prog_qr_present}, position={prog_qr_position}, info_length={len(prog_qr_info) if prog_qr_info else 0}, full_image_mapped={bool(full_image_qr_info)}")
        
        # Combine LLM and programmatic QR detection (prefer programmatic for presence, LLM for position)
        if not qr_code_position and prog_qr_present:
            qr_code_position = prog_qr_position
        
        # Text enrichment with context
        enrich_start = time.time()
        
        # Extract relevant context for this specific text
        abbreviations_context = ""
        org_context = ""
        personal_context_text = ""
        
        if raw_text and abbreviations_dict:
            relevant_abbrevs = extract_relevant_abbreviations(raw_text, abbreviations_dict)
            abbreviations_context = format_abbreviations_context(relevant_abbrevs)
        
        if raw_text and org_hierarchy and people_index:
            org_terms = extract_org_context_from_text(raw_text, org_hierarchy, people_index)
            org_context = format_org_context(org_terms)
        
        if raw_text and personal_context:
            relevant_personal = extract_relevant_context_for_text(raw_text, personal_context)
            personal_context_text = format_personal_context(relevant_personal)
        
        enrich_prompt = build_text_enrich_prompt(
            abbreviations_context=abbreviations_context,
            org_context=org_context,
            personal_context=personal_context_text
        )
        
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
    
    # For multi-image processing, group notes by image and create pages with sections
    # Use the enhanced text combining with spatial context
    vision_client, text_client = get_clients()
    
    pages = []
    for page_idx, (doc, image_path) in enumerate(zip(all_docs, image_paths)):
        page_number = page_idx + 1
        
        # Combine text with spatial context preservation
        combined_text = _combine_text_with_context(doc.notes)
        
        # Parse sections using dynamic semantic understanding
        sections = _parse_sections_from_text(combined_text, text_client)
        
        # Aggregate page-level metadata
        qr_present = any(note.qr_code_present for note in doc.notes)
        qr_position = None
        for note in doc.notes:
            if note.qr_code_present and note.qr_code_position:
                qr_position = note.qr_code_position
                break
        
        # Extract page title - check combined text for "Daily Notes: [date]" pattern
        page_title = None
        extracted_date = None
        
        # Extract date from combined text
        date_patterns = [
            r"(\d{1,2})/(\d{1,2})/(\d{2,4})",
            r"(\d{1,2})-(\d{1,2})-(\d{2,4})",
        ]
        for pattern in date_patterns:
            match = re.search(pattern, combined_text)
            if match:
                month, day, year = match.groups()
                if len(year) == 2:
                    year = "20" + year
                extracted_date = f"{month}/{day}/{year}"
                break
        
        # Look for "Daily Notes: [date]" pattern in combined text
        if extracted_date:
            title_patterns = [
                rf"##\s*(Daily\s+Notes:\s+{re.escape(extracted_date)})\s*##",
                rf"(Daily\s+Notes:\s+{re.escape(extracted_date)})",
            ]
            for pattern in title_patterns:
                match = re.search(pattern, combined_text, re.IGNORECASE)
                if match:
                    page_title = match.group(1).strip()
                    break
            
            # Fallback: check if "Daily" and "Notes: date" appear separately
            if not page_title:
                has_daily = "daily" in combined_text.lower()
                notes_date_match = re.search(rf"(Notes?):\s*{re.escape(extracted_date)}", combined_text, re.IGNORECASE)
                if has_daily and notes_date_match:
                    page_title = f"Daily Notes: {extracted_date}"
        
        # Fallback: check individual notes for titles
        if not page_title:
            for note in doc.notes:
                if note.title:
                    page_title = note.title
                    break
        
        # For page 2+, don't set title (only first page should have title)
        if page_number > 1:
            page_title = None
        
        # Build page sections with proper structure
        page_sections = []
        for section in sections:
            section_title = section.get("section_title")
            raw_text = section.get("raw_text", "")
            section_action_items = section.get("action_items", [])
            section_tags = section.get("tags", [])
            section_checkboxes = section.get("checkboxes", 0)
            
            # Always try to enrich section to get comprehensive action items and tags
            # Even if section parsing provided some, enrichment may find more
            try:
                enrich_prompt = build_text_enrich_prompt()
                enrich_response = text_client.generate(
                    f"Input note text:\n\n{raw_text}\n\n{enrich_prompt}",
                    max_tokens=settings.TEXT_AI_MODEL_MAX_OUTPUT_TOKENS,
                )
                
                if enrich_response and enrich_response.strip():
                    enrich_json_text = enrich_response.strip()
                    # Try extracting from markdown
                    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", enrich_json_text, re.DOTALL)
                    if json_match:
                        enrich_json_text = json_match.group(1).strip()
                    else:
                        json_match = re.search(r"(\{.*\})", enrich_json_text, re.DOTALL)
                        if json_match:
                            enrich_json_text = json_match.group(1).strip()
                    
                    enrich = json.loads(enrich_json_text)
                    enriched_action_items = enrich.get("action_items", [])
                    enriched_tags = enrich.get("tags", [])
                    
                    # Merge action items - prefer enriched ones if they're more comprehensive
                    if len(enriched_action_items) > len(section_action_items):
                        section_action_items = enriched_action_items
                    elif section_action_items and enriched_action_items:
                        # Combine and deduplicate
                        combined = list(section_action_items)
                        for ai in enriched_action_items:
                            if ai not in combined:
                                combined.append(ai)
                        section_action_items = combined
                    elif not section_action_items:
                        section_action_items = enriched_action_items
                    
                    # Merge tags
                    section_tags = list(set(section_tags + enriched_tags))
            except Exception as e:
                logger.debug(f"Failed to enrich section {section_title}: {e}")
                # Keep original action items if enrichment failed
            
            page_sections.append({
                "section_title": section_title,
                "raw_text": raw_text,
                "action_items": section_action_items or [],
                "tags": section_tags or [],
                "checkboxes": section_checkboxes
            })
        
        pages.append({
            "page_number": page_number,
            "title": page_title,
            "qr_code_present": qr_present,
            "qr_code_position": qr_position,
            "sections": page_sections
        })
    
    # Extract date from first page
    extracted_date = None
    if pages:
        first_page_text = " ".join(s.get("raw_text", "") for s in pages[0]["sections"])
        # Simple date extraction
        date_patterns = [
            r"(\d{1,2})/(\d{1,2})/(\d{2,4})",
            r"(\d{1,2})-(\d{1,2})-(\d{2,4})",
        ]
        for pattern in date_patterns:
            match = re.search(pattern, first_page_text)
            if match:
                month, day, year = match.groups()
                if len(year) == 2:
                    year = "20" + year
                extracted_date = f"{month}/{day}/{year}"
                break
    
    # Build summary
    total_sections = sum(len(page["sections"]) for page in pages)
    total_action_items = sum(
        len(s.get("action_items", []))
        for page in pages
        for s in page["sections"]
    )
    total_checkboxes = sum(
        s.get("checkboxes", 0)
        for page in pages
        for s in page["sections"]
    )
    
    # Write output with pages structure
    output = {
        "image_metadata": {
            "total_pages": len(pages),
            "date": extracted_date,
            "notebook_brand": notebook_brand,
            "detection_method": detection_method
        },
        "pages": pages,
        "summary": {
            "total_sections": total_sections,
            "total_action_items": total_action_items,
            "total_checkboxes": total_checkboxes,
            "main_themes": main_themes,
            "key_people_mentioned": [],
            "key_vendors_products": []
        }
    }
    
    Path(out_path).write_text(json.dumps(output, indent=2))
    logger.info(f"Aggregated {len(pages)} pages with {total_sections} sections from {len(image_paths)} images into {out_path}")


__all__ = ["process_image", "run_to_file", "process_multiple_images"]
