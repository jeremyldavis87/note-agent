"""
Context manager for efficient loading and caching of context data.

This module provides a centralized context manager that loads abbreviations,
organizational hierarchy, and personal context data with intelligent caching
to avoid repeated file I/O operations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List, Optional

from .abbreviations import (
    load_abbreviations_dict,
    extract_relevant_abbreviations,
    format_abbreviations_context,
)
from .org_hierarchy import (
    load_org_hierarchy,
    build_people_index,
    extract_org_context_from_text,
    format_org_context,
)
from .personal_context import (
    load_personal_context,
    extract_relevant_context_for_text,
    format_personal_context,
)


logger = logging.getLogger(__name__)


@dataclass
class ContextData:
    """Container for all context data."""
    abbreviations: Optional[Dict] = None
    org_hierarchy: Optional[Dict] = None
    people_index: Optional[Dict] = None
    personal_context: Optional[Dict] = None


class ContextManager:
    """
    Manages context data with caching to avoid repeated file I/O.
    
    This is a singleton-like class that loads context data once and
    caches it for subsequent requests.
    """
    
    _instance: Optional['ContextManager'] = None
    _context_data: Optional[ContextData] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._context_data = None
        return cls._instance
    
    def load_all(self, force_reload: bool = False) -> ContextData:
        """
        Load all context data with caching.
        
        Args:
            force_reload: Force reload even if cached
            
        Returns:
            ContextData object with all loaded context
        """
        if self._context_data is not None and not force_reload:
            return self._context_data
        
        logger.debug("Loading context data...")
        start_time = __import__('time').time()
        
        # Load abbreviations
        abbreviations = load_abbreviations_dict()
        logger.debug(f"Loaded abbreviations: {bool(abbreviations)}")
        
        # Load org hierarchy
        org_hierarchy = load_org_hierarchy()
        logger.debug(f"Loaded org hierarchy: {bool(org_hierarchy)}")
        
        # Build people index
        people_index = None
        if org_hierarchy:
            people_index = build_people_index(org_hierarchy)
            all_people = people_index.get("all_people", []) if people_index else []
            logger.debug(f"Built people index: {len(all_people)} people")
        
        # Load personal context
        personal_context = load_personal_context()
        logger.debug(f"Loaded personal context: {bool(personal_context)}")
        
        duration = __import__('time').time() - start_time
        logger.debug(f"Context loading completed in {duration:.3f}s")
        
        self._context_data = ContextData(
            abbreviations=abbreviations,
            org_hierarchy=org_hierarchy,
            people_index=people_index,
            personal_context=personal_context,
        )
        
        return self._context_data
    
    def get_vision_context(self) -> str:
        """
        Get formatted context for vision prompt.
        
        For vision phase, we include all abbreviations to help with OCR.
        
        Returns:
            Formatted context string for vision prompt
        """
        data = self.load_all()
        
        if data.abbreviations:
            return format_abbreviations_context(data.abbreviations)
        
        return ""
    
    def get_enrichment_context(self, text: str) -> Dict[str, str]:
        """
        Get formatted context for text enrichment based on extracted text.
        
        Args:
            text: Extracted text to analyze for relevant context
            
        Returns:
            Dictionary with context types as keys and formatted strings as values
        """
        data = self.load_all()
        context = {}
        
        # Extract relevant abbreviations
        if text and data.abbreviations:
            relevant_abbrevs = extract_relevant_abbreviations(text, data.abbreviations)
            if relevant_abbrevs:
                context['abbreviations'] = format_abbreviations_context(relevant_abbrevs)
        
        # Extract org context
        if text and data.org_hierarchy and data.people_index:
            org_terms = extract_org_context_from_text(text, data.org_hierarchy, data.people_index)
            if org_terms:
                context['org'] = format_org_context(org_terms)
        
        # Extract personal context
        if text and data.personal_context:
            relevant_personal = extract_relevant_context_for_text(text, data.personal_context)
            if relevant_personal:
                context['personal'] = format_personal_context(relevant_personal)
        
        return context
    
    def clear_cache(self):
        """Clear cached context data to force reload."""
        self._context_data = None
        logger.debug("Context cache cleared")
    
    @property
    def is_loaded(self) -> bool:
        """Check if context data is loaded."""
        return self._context_data is not None
    
    @property
    def abbreviations(self) -> Optional[Dict]:
        """Get cached abbreviations."""
        if self._context_data:
            return self._context_data.abbreviations
        return None
    
    @property
    def org_hierarchy(self) -> Optional[Dict]:
        """Get cached org hierarchy."""
        if self._context_data:
            return self._context_data.org_hierarchy
        return None
    
    @property
    def people_index(self) -> Optional[Dict]:
        """Get cached people index."""
        if self._context_data:
            return self._context_data.people_index
        return None
    
    @property
    def personal_context(self) -> Optional[Dict]:
        """Get cached personal context."""
        if self._context_data:
            return self._context_data.personal_context
        return None


# Singleton instance for easy access
_context_manager = ContextManager()


def get_context_manager() -> ContextManager:
    """Get the global context manager instance."""
    return _context_manager


__all__ = [
    "ContextData",
    "ContextManager",
    "get_context_manager",
]

