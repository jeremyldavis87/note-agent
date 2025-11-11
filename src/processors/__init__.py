"""
Processors package for handling different processing tasks.

This package contains specialized processors for:
- Region processing (individual note regions)
- Section parsing (multi-page documents)
- Text enrichment
"""

from .region_processor import RegionProcessor

__all__ = ["RegionProcessor"]

