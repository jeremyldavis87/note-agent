from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import numpy as np


@dataclass
class Region:
    bbox: Tuple[int, int, int, int]  # x, y, w, h
    position_label: str              # e.g., row_1_col_1


def split_three_by_three(image: np.ndarray) -> List[Region]:
    h, w = image.shape[:2]
    regions: List[Region] = []
    cell_w = w // 3
    cell_h = h // 3
    for r in range(3):
        for c in range(3):
            x = c * cell_w
            y = r * cell_h
            regions.append(Region(bbox=(x, y, cell_w, cell_h), position_label=f"row_{r+1}_col_{c+1}"))
    return regions


def detect_regions(image: np.ndarray, force_single: bool = False) -> List[Region]:
    if force_single:
        h, w = image.shape[:2]
        return [Region(bbox=(0, 0, w, h), position_label="row_1_col_1")]
    # Heuristic: assume Rocketbook 3x3 layout by default
    return split_three_by_three(image)


__all__ = ["Region", "detect_regions"]
