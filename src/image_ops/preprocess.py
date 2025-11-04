from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import cv2
import numpy as np


@dataclass
class PreprocessResult:
    image: np.ndarray
    metrics: dict


def ensure_bgr(image: np.ndarray) -> np.ndarray:
    """
    Ensure an image is in BGR format, converting from grayscale if needed.
    
    Args:
        image: Input image (BGR or grayscale)
        
    Returns:
        BGR image (3 channels)
    """
    if len(image.shape) == 2:
        # Grayscale to BGR
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    return image


def preprocess_image(bgr: np.ndarray) -> PreprocessResult:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    # Contrast stretching
    p2, p98 = np.percentile(denoised, (2, 98))
    stretched = np.clip((denoised - p2) * 255.0 / max(p98 - p2, 1), 0, 255).astype(np.uint8)
    # Deskew heuristic (skip heavy ops for speed)
    metrics = {
        "width": int(bgr.shape[1]),
        "height": int(bgr.shape[0]),
        "channels": int(bgr.shape[2]) if len(bgr.shape) == 3 else 1,
        "contrast_range": float(p98 - p2),
    }
    return PreprocessResult(image=stretched, metrics=metrics)


__all__ = ["preprocess_image", "PreprocessResult", "ensure_bgr"]
