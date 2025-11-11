"""
Utility functions and classes for common operations.

This module provides reusable utilities for:
- JSON parsing and extraction
- Regex pattern compilation and caching
- Common text operations
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any, Dict, Optional, Pattern


class JSONParser:
    """Robust JSON parser with support for markdown code blocks and fallback."""
    
    @staticmethod
    def extract_and_parse(text: str, expected_type: type = dict) -> Any:
        """
        Extract and parse JSON from text that may contain markdown or extra content.
        
        Args:
            text: Raw text potentially containing JSON
            expected_type: Expected type (dict or list)
            
        Returns:
            Parsed JSON object or fallback value
            
        Raises:
            json.JSONDecodeError: If parsing fails and no fallback is possible
        """
        if not text or not isinstance(text, str):
            if expected_type == list:
                return []
            return {}
        
        text = text.strip()
        
        # Try direct parsing first
        try:
            data = json.loads(text)
            if isinstance(data, expected_type):
                return data
        except json.JSONDecodeError:
            pass
        
        # Try extracting from markdown code blocks
        if expected_type == dict:
            pattern = r"```(?:json)?\s*(\{.*?\})\s*```"
        else:  # list
            pattern = r"```(?:json)?\s*(\[.*?\])\s*```"
        
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                if isinstance(data, expected_type):
                    return data
            except json.JSONDecodeError:
                pass
        
        # Try finding JSON by brace/bracket matching
        if expected_type == dict:
            start_char, end_char = "{", "}"
        else:  # list
            start_char, end_char = "[", "]"
        
        start_idx = text.find(start_char)
        if start_idx != -1:
            count = 0
            end_idx = -1
            for i in range(start_idx, len(text)):
                if text[i] == start_char:
                    count += 1
                elif text[i] == end_char:
                    count -= 1
                    if count == 0:
                        end_idx = i + 1
                        break
            
            if end_idx != -1:
                try:
                    data = json.loads(text[start_idx:end_idx])
                    if isinstance(data, expected_type):
                        return data
                except json.JSONDecodeError:
                    pass
        
        # Fallback
        if expected_type == list:
            return []
        return {}
    
    @staticmethod
    def parse_or_default(text: str, default: Any = None) -> Any:
        """
        Try to parse JSON, return default on failure.
        
        Args:
            text: Text to parse
            default: Default value to return on error
            
        Returns:
            Parsed JSON or default value
        """
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError, AttributeError):
            return default if default is not None else {}


class RegexCache:
    """Cache for compiled regex patterns to avoid repeated compilation."""
    
    _cache: Dict[str, Pattern] = {}
    
    @classmethod
    @lru_cache(maxsize=128)
    def get(cls, pattern: str, flags: int = 0) -> Pattern:
        """
        Get or compile a regex pattern with caching.
        
        Args:
            pattern: Regex pattern string
            flags: Regex flags
            
        Returns:
            Compiled pattern object
        """
        cache_key = f"{pattern}:{flags}"
        if cache_key not in cls._cache:
            cls._cache[cache_key] = re.compile(pattern, flags)
        return cls._cache[cache_key]


class TextUtils:
    """Common text processing utilities."""
    
    @staticmethod
    def normalize_bullets(text: str) -> str:
        """Convert dash bullets to unicode bullet points."""
        return text.replace("- ", "• ")
    
    @staticmethod
    def count_checkboxes(text: str) -> int:
        """Count checkbox characters in text."""
        return text.count("☐") + text.count("☑")
    
    @staticmethod
    def extract_title_from_double_hash(text: str) -> Optional[str]:
        """
        Extract title from ##Title## syntax.
        
        Args:
            text: Text to search
            
        Returns:
            Extracted title or None
        """
        pattern = RegexCache.get(r"##([^#]+)##")
        match = pattern.search(text)
        if match:
            title = match.group(1).strip()
            return title if title else None
        return None
    
    @staticmethod
    def normalize_title(title: Optional[str]) -> Optional[str]:
        """
        Normalize a title by stripping whitespace and handling 'null' strings.
        
        Args:
            title: Title to normalize
            
        Returns:
            Normalized title or None
        """
        if not title:
            return None
        
        title_str = str(title).strip()
        if title_str == "null" or not title_str:
            return None
        
        return title_str


__all__ = [
    "JSONParser",
    "RegexCache",
    "TextUtils",
]

