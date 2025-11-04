"""Abbreviations dictionary management for agent context."""

from __future__ import annotations

import re
from typing import Any, Dict

from ..logging_setup import setup_logging
import logging
from .utils import _load_context_file

logger = logging.getLogger(__name__)


def _validate_abbreviations(data: Any) -> bool:
    """
    Validate that the abbreviations data has the correct structure.
    
    Args:
        data: The loaded JSON data
        
    Returns:
        True if valid, False otherwise
    """
    if not isinstance(data, dict):
        return False
    return True


def load_abbreviations_dict() -> Dict[str, Dict[str, str]]:
    """
    Load abbreviations dictionary from agent-context/abbreviations.json.
    
    Returns:
        Dictionary mapping abbreviation keys to their full_form and description.
        Returns empty dict if file is missing or malformed.
    """
    data = _load_context_file(
        "abbreviations.json",
        validate_func=_validate_abbreviations,
        description="abbreviations"
    )
    
    # Validate each entry has full_form and description
    validated = {}
    for key, value in data.items():
        if isinstance(value, dict) and "full_form" in value and "description" in value:
            validated[key] = value
        else:
            logger.warning(f"Invalid structure for abbreviation '{key}', skipping")
    
    if validated:
        logger.info(f"Loaded {len(validated)} abbreviations from dictionary")
    
    return validated


def extract_relevant_abbreviations(
    raw_text: str, 
    abbreviations: Dict[str, Dict[str, str]]
) -> Dict[str, Dict[str, str]]:
    """
    Extract only abbreviations that appear in the raw_text.
    
    Args:
        raw_text: The text content to search for abbreviations
        abbreviations: Full abbreviations dictionary
        
    Returns:
        Dictionary containing only abbreviations that appear in the text
    """
    if not abbreviations:
        return {}
    
    # Case-insensitive matching - look for abbreviation keys in the text
    text_upper = raw_text.upper()
    relevant = {}
    
    for abbrev_key, abbrev_data in abbreviations.items():
        # Check if abbreviation appears in text (case-insensitive)
        # Look for word boundaries to avoid partial matches
        pattern = r'\b' + re.escape(abbrev_key.upper()) + r'\b'
        if re.search(pattern, text_upper):
            relevant[abbrev_key] = abbrev_data
    
    return relevant


def format_abbreviations_context(abbreviations: Dict[str, Dict[str, str]]) -> str:
    """
    Format abbreviations dictionary into a readable string for prompt injection.
    
    Args:
        abbreviations: Dictionary of abbreviations to format
        
    Returns:
        Formatted string describing the abbreviations, or empty string if none
    """
    if not abbreviations:
        return ""
    
    lines = ["Additional context - abbreviations and terms found in the text:"]
    
    for abbrev_key, abbrev_data in sorted(abbreviations.items()):
        full_form = abbrev_data.get("full_form", "")
        description = abbrev_data.get("description", "")
        
        line = f"- {abbrev_key}"
        if full_form and full_form != abbrev_key:
            line += f" ({full_form})"
        if description:
            line += f": {description}"
        
        lines.append(line)
    
    return "\n".join(lines)


__all__ = [
    "load_abbreviations_dict",
    "extract_relevant_abbreviations",
    "format_abbreviations_context",
]
