"""Shared utilities for context modules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import logging

logger = logging.getLogger(__name__)


def _load_context_file(
    filename: str,
    validate_func: Optional[Callable[[Any], bool]] = None,
    description: str = "context"
) -> Dict:
    """
    Load a JSON context file from agent-context directory.
    
    Args:
        filename: Name of the JSON file (e.g., "abbreviations.json")
        validate_func: Optional function to validate the loaded data structure.
                       Should return True if valid, False otherwise.
                       If None, only checks that data is a dict.
        description: Description of the context for logging (e.g., "abbreviations")
        
    Returns:
        Dictionary containing the loaded context data.
        Returns empty dict if file is missing or malformed.
    """
    try:
        # Find project root (where agent-context/ directory is)
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent.parent
        context_path = project_root / "agent-context" / filename
        
        if not context_path.exists():
            logger.warning(f"{description.capitalize()} file not found at {context_path}")
            return {}
        
        with open(context_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Validate structure
        if validate_func:
            if not validate_func(data):
                logger.warning(f"{description.capitalize()} file does not have expected structure")
                return {}
        else:
            # Default validation: must be a dict
            if not isinstance(data, dict):
                logger.warning(f"{description.capitalize()} file does not contain a dictionary")
                return {}
        
        logger.info(f"Loaded {description} from {context_path}")
        return data
        
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse {filename}: {e}")
        return {}
    except Exception as e:
        logger.warning(f"Error loading {description} dictionary: {e}")
        return {}


__all__ = ["_load_context_file"]

