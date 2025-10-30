from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import cv2
import numpy as np


@dataclass
class PreprocessResult:
    image: np.ndarray
    metrics: dict


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


__all__ = ["preprocess_image", "PreprocessResult"]
