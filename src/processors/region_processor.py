"""
Region processor for handling individual note region processing.

This module extracts the region processing logic from the main pipeline,
making it more testable and maintainable.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, Optional, Tuple

import cv2
import numpy as np

from ..config import settings
from ..schema import Note
from ..detect.multinote import Region
from ..llm.base import VisionInput, LLMClient
from ..image_ops.qr import detect_qr_in_region, get_qr_code_info
from ..image_ops.color import validate_note_color
from ..parsers import VisionResponseParser, EnrichmentResponseParser
from ..utils import TextUtils
from ..exceptions import RegionProcessingError, InvalidBBoxError, VisionExtractionError
from ..context.manager import get_context_manager


logger = logging.getLogger(__name__)


class RegionProcessor:
    """
    Processes individual note regions to extract text and metadata.
    
    This class encapsulates all the logic for processing a single region,
    making it easier to test and maintain.
    """
    
    def __init__(
        self,
        vision_client: LLMClient,
        text_client: LLMClient,
        vision_prompt: str,
        qr_to_region_map: Optional[Dict[int, list]] = None,
    ):
        """
        Initialize region processor.
        
        Args:
            vision_client: LLM client for vision extraction
            text_client: LLM client for text enrichment
            vision_prompt: Prompt for vision extraction
            qr_to_region_map: Mapping of region indices to QR codes
        """
        self.vision_client = vision_client
        self.text_client = text_client
        self.vision_prompt = vision_prompt
        self.qr_to_region_map = qr_to_region_map or {}
        self.context_manager = get_context_manager()
    
    def process(self, region: Region, region_idx: int, image: np.ndarray) -> Note:
        """
        Process a single region to extract note data.
        
        Args:
            region: Region object with bbox and position
            region_idx: Index of the region
            image: Full BGR image
            
        Returns:
            Note object with extracted data
            
        Raises:
            RegionProcessingError: If processing fails
        """
        start_time = time.time()
        x, y, w, h = region.bbox
        
        logger.info(
            f"Region {region_idx} ({region.position_label}): Starting processing - "
            f"bbox=({x}, {y}, {w}, {h})"
        )
        
        try:
            # Validate and extract region
            region_img = self._extract_and_validate_region(image, region.bbox, region_idx)
            
            # Vision extraction
            raw_text, note_color, llm_qr_present, llm_qr_position = self._extract_with_vision(
                region_img, region_idx
            )
            
            # QR detection
            qr_code_present, qr_code_position, qr_code_info = self._detect_qr_code(
                region_img, region_idx, llm_qr_present, llm_qr_position, region.bbox, image.shape
            )
            
            # Text enrichment
            title, action_items, tags = self._enrich_text(raw_text, region_idx)
            
            # Create note
            note = Note(
                position=region.position_label,
                note_color=note_color,
                qr_code_present=qr_code_present,
                qr_code_position=qr_code_position,
                qr_code_info=qr_code_info,
                title=title,
                header=None,
                raw_text=raw_text,
                formatted_text=TextUtils.normalize_bullets(raw_text),
                action_items=action_items,
                tags=tags,
                checkboxes=TextUtils.count_checkboxes(raw_text) or None,
                confidence_score=0.9,
                processing_method="vision_llm",
            )
            
            duration = time.time() - start_time
            logger.info(
                f"Region {region_idx} ({region.position_label}): "
                f"Completed processing in {duration:.3f}s"
            )
            
            return note
        
        except Exception as e:
            duration = time.time() - start_time
            error_msg = (
                f"Region {region_idx} ({region.position_label}): "
                f"Processing failed - {type(e).__name__}: {str(e)}"
            )
            logger.error(error_msg, exc_info=True)
            logger.error(f"Region {region_idx}: Failed after {duration:.3f}s")
            
            # Return error note instead of raising
            return self._create_error_note(region.position_label, error_msg)
    
    def _extract_and_validate_region(
        self, image: np.ndarray, bbox: Tuple[int, int, int, int], region_idx: int
    ) -> np.ndarray:
        """
        Extract and validate a region from the image.
        
        Args:
            image: Full BGR image
            bbox: Bounding box (x, y, w, h)
            region_idx: Region index for error messages
            
        Returns:
            Extracted region image
            
        Raises:
            InvalidBBoxError: If bbox is invalid
        """
        x, y, w, h = bbox
        img_h, img_w = image.shape[:2]
        
        # Validate bbox coordinates
        if x < 0 or y < 0 or w <= 0 or h <= 0:
            raise InvalidBBoxError(bbox, image.shape)
        
        # Clamp coordinates to image bounds
        x = max(0, min(x, img_w - 1))
        y = max(0, min(y, img_h - 1))
        w = min(w, img_w - x)
        h = min(h, img_h - y)
        
        if w <= 0 or h <= 0:
            raise InvalidBBoxError((x, y, w, h), image.shape)
        
        # Extract region image
        region_img = image[y:y+h, x:x+w]
        
        # Validate extracted region is non-empty
        if region_img.size == 0 or region_img.shape[0] == 0 or region_img.shape[1] == 0:
            raise RegionProcessingError(
                f"Extracted region image is empty - shape={region_img.shape}",
                region_index=region_idx
            )
        
        logger.debug(
            f"Region {region_idx}: Extracted region image - "
            f"shape={region_img.shape}, size={region_img.size} bytes"
        )
        
        return region_img
    
    def _extract_with_vision(
        self, region_img: np.ndarray, region_idx: int
    ) -> Tuple[str, Optional[str], Optional[bool], Optional[str]]:
        """
        Extract text and metadata using vision LLM.
        
        Args:
            region_img: Region image
            region_idx: Region index
            
        Returns:
            Tuple of (raw_text, note_color, qr_present, qr_position)
            
        Raises:
            VisionExtractionError: If vision extraction fails
        """
        vision_start = time.time()
        
        # Convert image to JPEG bytes
        _, img_bytes = cv2.imencode('.jpg', region_img)
        if img_bytes is None or img_bytes.size == 0:
            raise VisionExtractionError(f"Region {region_idx}: Failed to encode image to JPEG")
        
        # Call vision LLM
        vision_input = VisionInput(image_bytes=img_bytes.tobytes(), instructions=self.vision_prompt)
        vision_response = self.vision_client.generate(vision_input)
        
        vision_duration = time.time() - vision_start
        
        # Validate response
        if vision_response is None:
            logger.warning(f"Region {region_idx}: Vision client returned None, using empty string")
            vision_response = ""
        
        logger.debug(
            f"Region {region_idx}: vision extraction completed in {vision_duration:.3f}s, "
            f"response length={len(vision_response) if vision_response else 0}"
        )
        
        # Parse response
        parsed = VisionResponseParser.parse(vision_response)
        
        # Validate note color with region image
        note_color = parsed.note_color
        if note_color:
            note_color = validate_note_color(region_img, note_color)
        
        return parsed.raw_text, note_color, parsed.qr_code_present, parsed.qr_code_position
    
    def _detect_qr_code(
        self,
        region_img: np.ndarray,
        region_idx: int,
        llm_qr_present: Optional[bool],
        llm_qr_position: Optional[str],
        bbox: Tuple[int, int, int, int],
        image_shape: Tuple[int, int]
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Detect QR code in region using programmatic detection and full-image mapping.
        
        Args:
            region_img: Region image
            region_idx: Region index
            llm_qr_present: LLM's QR detection result
            llm_qr_position: LLM's QR position result
            bbox: Region bounding box
            image_shape: Full image shape
            
        Returns:
            Tuple of (qr_present, qr_position, qr_info)
        """
        qr_start = time.time()
        
        # Programmatic QR detection on region
        qr_result = detect_qr_in_region(region_img)
        
        if qr_result is None:
            prog_qr_present = False
            prog_qr_position = None
            prog_qr_info = None
        else:
            prog_qr_position, prog_qr_info, _ = qr_result
            prog_qr_present = True
        
        # Check full image QR mapping
        full_image_qr_info = None
        if region_idx in self.qr_to_region_map:
            qr_data, qr_coords = self.qr_to_region_map[region_idx][0]
            full_image_qr_info = qr_data
            
            if not prog_qr_present:
                prog_qr_present = True
                # Calculate position relative to region
                x, y, w, h = bbox
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
        
        # Combine LLM and programmatic results
        qr_code_present = prog_qr_present or llm_qr_present
        qr_code_position = prog_qr_position or llm_qr_position
        qr_code_info = full_image_qr_info or prog_qr_info
        
        qr_duration = time.time() - qr_start
        logger.debug(
            f"Region {region_idx}: QR detection completed in {qr_duration:.3f}s: "
            f"present={prog_qr_present}, position={prog_qr_position}, "
            f"info_length={len(prog_qr_info) if prog_qr_info else 0}, "
            f"full_image_mapped={bool(full_image_qr_info)}"
        )
        
        return qr_code_present, qr_code_position, qr_code_info
    
    def _enrich_text(
        self, raw_text: str, region_idx: int
    ) -> Tuple[Optional[str], list, list]:
        """
        Enrich text with context and extract metadata.
        
        Args:
            raw_text: Raw extracted text
            region_idx: Region index
            
        Returns:
            Tuple of (title, action_items, tags)
        """
        enrich_start = time.time()
        
        # Get relevant context for this text
        context_dict = self.context_manager.get_enrichment_context(raw_text)
        
        # Build enrichment prompt
        from ..prompts import build_text_enrich_prompt
        enrich_prompt = build_text_enrich_prompt(
            abbreviations_context=context_dict.get('abbreviations', ''),
            org_context=context_dict.get('org', ''),
            personal_context=context_dict.get('personal', '')
        )
        
        # Call text LLM
        enrich_json = self.text_client.generate(
            f"Input note text:\n\n{raw_text}\n\n{enrich_prompt}",
            max_tokens=settings.TEXT_AI_MODEL_MAX_OUTPUT_TOKENS,
        )
        
        enrich_duration = time.time() - enrich_start
        logger.debug(
            f"Region {region_idx}: text enrichment completed in {enrich_duration:.3f}s, "
            f"output length={len(enrich_json)}"
        )
        
        # Parse enrichment response
        enrichment = EnrichmentResponseParser.parse(enrich_json, fallback_text=raw_text)
        
        logger.debug(
            f"Region {region_idx}: parsed enrichment, "
            f"action_items={len(enrichment.action_items)}, tags={len(enrichment.tags)}"
        )
        
        if enrichment.title:
            logger.debug(f"Region {region_idx}: title={enrichment.title}")
        
        return enrichment.title, enrichment.action_items, enrichment.tags
    
    def _create_error_note(self, position: str, error_msg: str) -> Note:
        """Create an error note for failed processing."""
        return Note(
            position=position,
            note_color=None,
            qr_code_present=None,
            qr_code_position=None,
            qr_code_info=None,
            title=None,
            header=None,
            raw_text=f"ERROR: {error_msg}",
            formatted_text=f"ERROR: {error_msg}",
            action_items=[],
            tags=[],
            checkboxes=None,
            confidence_score=0.0,
            processing_method="vision_llm",
        )


__all__ = ["RegionProcessor"]

