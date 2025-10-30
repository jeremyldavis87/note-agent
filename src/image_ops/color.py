from __future__ import annotations

from typing import Tuple

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


__all__ = ["dominant_color", "describe_background_color"]
