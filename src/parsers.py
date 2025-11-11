"""
Response parsers for LLM outputs.

This module provides specialized parsers for different types of LLM responses,
consolidating the JSON parsing logic that was previously scattered throughout
the codebase.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .utils import JSONParser, TextUtils
from .exceptions import JSONParsingError


logger = logging.getLogger(__name__)


@dataclass
class VisionResponse:
    """Parsed vision LLM response."""
    raw_text: str
    note_color: Optional[str] = None
    qr_code_present: Optional[bool] = None
    qr_code_position: Optional[str] = None


@dataclass
class EnrichmentResponse:
    """Parsed text enrichment LLM response."""
    title: Optional[str] = None
    action_items: List[str] = None
    tags: List[str] = None
    
    def __post_init__(self):
        if self.action_items is None:
            self.action_items = []
        if self.tags is None:
            self.tags = []


@dataclass
class SectionData:
    """Parsed section data from section parsing."""
    section_title: Optional[str] = None
    raw_text: str = ""
    action_items: List[str] = None
    tags: List[str] = None
    checkboxes: int = 0
    
    def __post_init__(self):
        if self.action_items is None:
            self.action_items = []
        if self.tags is None:
            self.tags = []


class VisionResponseParser:
    """Parser for vision LLM responses."""
    
    @staticmethod
    def parse(content: str) -> VisionResponse:
        """
        Parse vision LLM response to extract text and metadata.
        
        Handles both structured JSON responses (new format) and plain text (backward compatibility).
        
        Args:
            content: Raw response from vision LLM
            
        Returns:
            VisionResponse with extracted data
        """
        # Handle None or empty content
        if content is None:
            return VisionResponse(raw_text="")
        
        if not isinstance(content, str):
            content = str(content)
        
        content = content.strip()
        
        # Try to parse as JSON first
        data = JSONParser.extract_and_parse(content, expected_type=dict)
        
        if data and isinstance(data, dict):
            raw_text = data.get("text", "")
            note_color = data.get("note_color")
            qr_code_present = data.get("qr_code_present")
            qr_code_position = data.get("qr_code_position")
            
            return VisionResponse(
                raw_text=raw_text,
                note_color=note_color,
                qr_code_present=qr_code_present,
                qr_code_position=qr_code_position,
            )
        
        # Fallback: treat entire response as plain text
        return VisionResponse(raw_text=content)


class EnrichmentResponseParser:
    """Parser for text enrichment LLM responses."""
    
    @staticmethod
    def parse(content: str, fallback_text: str = "") -> EnrichmentResponse:
        """
        Parse text enrichment response.
        
        Args:
            content: Raw response from text enrichment LLM
            fallback_text: Text to use for title extraction if parsing fails
            
        Returns:
            EnrichmentResponse with extracted data
        """
        if not content or not isinstance(content, str):
            return EnrichmentResponse()
        
        # Try to parse JSON
        data = JSONParser.extract_and_parse(content, expected_type=dict)
        
        if not data or not isinstance(data, dict):
            logger.warning("Failed to parse enrichment response, using empty defaults")
            return EnrichmentResponse()
        
        # Extract title with normalization
        title = TextUtils.normalize_title(data.get("title"))
        
        # Fallback to regex extraction if no title from LLM
        if not title and fallback_text:
            title = TextUtils.extract_title_from_double_hash(fallback_text)
        
        # Extract action items and tags
        action_items = data.get("action_items", [])
        tags = data.get("tags", [])
        
        # Ensure they're lists
        if not isinstance(action_items, list):
            action_items = []
        if not isinstance(tags, list):
            tags = []
        
        return EnrichmentResponse(
            title=title,
            action_items=action_items,
            tags=tags,
        )


class SectionParser:
    """Parser for section parsing responses."""
    
    @staticmethod
    def parse(content: str, fallback_text: str = "") -> List[SectionData]:
        """
        Parse section parsing response.
        
        Args:
            content: Raw response from section parsing LLM
            fallback_text: Original text to use as fallback
            
        Returns:
            List of SectionData objects
        """
        if not content or not isinstance(content, str):
            logger.warning("Empty response from section parsing")
            return [SectionParser._create_fallback_section(fallback_text)]
        
        # Try to parse as JSON array
        try:
            sections_data = JSONParser.extract_and_parse(content, expected_type=list)
            
            if not isinstance(sections_data, list):
                # Check if it's wrapped in a dict
                if isinstance(sections_data, dict) and "sections" in sections_data:
                    sections_data = sections_data["sections"]
                else:
                    logger.warning("Section parsing did not return array, using fallback")
                    return [SectionParser._create_fallback_section(fallback_text)]
            
            # Parse each section
            sections = []
            for section_dict in sections_data:
                if not isinstance(section_dict, dict):
                    continue
                
                section = SectionData(
                    section_title=section_dict.get("section_title"),
                    raw_text=section_dict.get("raw_text", ""),
                    action_items=section_dict.get("action_items", []),
                    tags=section_dict.get("tags", []),
                    checkboxes=section_dict.get("checkboxes", 0),
                )
                sections.append(section)
            
            return sections if sections else [SectionParser._create_fallback_section(fallback_text)]
        
        except Exception as e:
            logger.warning(f"Failed to parse sections: {e}")
            return [SectionParser._create_fallback_section(fallback_text)]
    
    @staticmethod
    def _create_fallback_section(text: str) -> SectionData:
        """Create a single fallback section with the entire text."""
        return SectionData(
            section_title=None,
            raw_text=text,
            action_items=[],
            tags=[],
            checkboxes=TextUtils.count_checkboxes(text),
        )


__all__ = [
    "VisionResponse",
    "EnrichmentResponse",
    "SectionData",
    "VisionResponseParser",
    "EnrichmentResponseParser",
    "SectionParser",
]

