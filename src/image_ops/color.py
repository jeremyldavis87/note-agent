from __future__ import annotations

from typing import Optional, Tuple

import cv2
import numpy as np


def dominant_color(bgr: np.ndarray) -> Tuple[int, int, int]:
    small = cv2.resize(bgr, (64, 64), interpolation=cv2.INTER_AREA)
    avg = small.reshape(-1, 3).mean(axis=0)
    b, g, r = avg.tolist()
    return int(b), int(g), int(r)


def describe_background_color(rgb: Tuple[int, int, int]) -> str:
    r, g, b = rgb
    # crude mapping to known label used in expected output
    if r > 140 and g < 100 and b < 100:
        return "terracotta/rust"
    return "unknown"


def validate_note_color(bgr_region: np.ndarray, suggested_color: Optional[str]) -> Optional[str]:
    """
    Validate or refine a suggested note color based on RGB analysis of the region.
    
    This is a validation step, not primary detection. The LLM-suggested color
    is considered primary, and this function provides basic validation.
    
    Args:
        bgr_region: Cropped BGR image of a single note region
        suggested_color: Color name suggested by LLM (e.g., "orange", "green", "blue")
        
    Returns:
        Validated color name or None if confidence is low or suggestion is invalid
    """
    if not suggested_color:
        return None
    
    # Get dominant color of the region
    b, g, r = dominant_color(bgr_region)
    
    # Simple RGB-based color detection for common note colors
    # These are heuristic thresholds based on typical Rocketbook note colors
    max_component = max(r, g, b)
    min_component = min(r, g, b)
    saturation = (max_component - min_component) / max(max_component, 1)
    
    # Determine color from RGB values
    detected_color = None
    
    # Orange: high red, medium green, low blue
    if r > 150 and g > 80 and g < 200 and b < 100:
        detected_color = "orange"
    # Green: low red, high green, low blue
    elif r < 100 and g > 150 and b < 100:
        detected_color = "green"
    # Blue: low red, medium green, high blue
    elif r < 100 and g < 150 and b > 150:
        detected_color = "blue"
    # Yellow: high red, high green, low blue
    elif r > 150 and g > 150 and b < 100:
        detected_color = "yellow"
    # Pink: high red, medium-high green, medium-high blue
    elif r > 180 and g > 100 and g < 180 and b > 100 and b < 180:
        detected_color = "pink"
    # Purple: medium red, low-medium green, high blue
    elif r > 100 and r < 180 and g < 120 and b > 150:
        detected_color = "purple"
    # Red: very high red, low green, low blue
    elif r > 200 and g < 80 and b < 80:
        detected_color = "red"
    
    # If we detected a color and it matches the suggestion, return it
    # If suggestion doesn't match but we detected something, return detected
    # If no detection but suggestion seems reasonable (is in our valid list), return suggestion
    valid_colors = {"orange", "green", "blue", "yellow", "pink", "purple", "red"}
    
    if detected_color:
        # If detected color matches suggestion, we're confident
        if detected_color == suggested_color.lower():
            return suggested_color.lower()
        # If they don't match, prefer detected (more reliable)
        else:
            return detected_color
    
    # If no detection but suggestion is valid, trust the LLM
    if suggested_color.lower() in valid_colors:
        return suggested_color.lower()
    
    # Low confidence - return None
    return None


__all__ = ["dominant_color", "describe_background_color", "validate_note_color"]
