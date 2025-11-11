"""
Custom exception classes for better error handling.

This module provides domain-specific exceptions that make error handling
more explicit and maintainable throughout the codebase.
"""

from __future__ import annotations

from typing import Optional


class NoteAgentError(Exception):
    """Base exception for all note agent errors."""
    pass


class ImageProcessingError(NoteAgentError):
    """Raised when image processing fails."""
    
    def __init__(self, message: str, image_path: Optional[str] = None):
        self.image_path = image_path
        super().__init__(message)


class RegionProcessingError(NoteAgentError):
    """Raised when a specific region fails to process."""
    
    def __init__(self, message: str, region_index: Optional[int] = None, position: Optional[str] = None):
        self.region_index = region_index
        self.position = position
        super().__init__(message)


class VisionExtractionError(NoteAgentError):
    """Raised when vision LLM extraction fails."""
    pass


class TextEnrichmentError(NoteAgentError):
    """Raised when text enrichment fails."""
    pass


class JSONParsingError(NoteAgentError):
    """Raised when JSON parsing fails in a critical context."""
    
    def __init__(self, message: str, raw_content: Optional[str] = None):
        self.raw_content = raw_content
        super().__init__(message)


class DetectionError(NoteAgentError):
    """Raised when region/note detection fails."""
    pass


class ContextLoadError(NoteAgentError):
    """Raised when loading context data fails."""
    
    def __init__(self, message: str, context_type: Optional[str] = None):
        self.context_type = context_type
        super().__init__(message)


class InvalidBBoxError(RegionProcessingError):
    """Raised when a bounding box has invalid coordinates."""
    
    def __init__(self, bbox: tuple, image_shape: Optional[tuple] = None):
        self.bbox = bbox
        self.image_shape = image_shape
        message = f"Invalid bounding box: {bbox}"
        if image_shape:
            message += f" for image shape {image_shape}"
        super().__init__(message)


__all__ = [
    "NoteAgentError",
    "ImageProcessingError",
    "RegionProcessingError",
    "VisionExtractionError",
    "TextEnrichmentError",
    "JSONParsingError",
    "DetectionError",
    "ContextLoadError",
    "InvalidBBoxError",
]

