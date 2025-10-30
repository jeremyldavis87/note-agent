from __future__ import annotations

from typing import List, Tuple

import cv2
from pyzbar.pyzbar import decode, ZBarSymbol


def detect_qr_positions(bgr) -> List[Tuple[str, Tuple[int, int, int, int]]]:
    results = []
    for angle in (0, 90, 180, 270):
        if angle:
            rot = cv2.rotate(bgr, getattr(cv2, f"ROTATE_{angle}_CLOCKWISE") if angle in (90,) else cv2.ROTATE_180)
        else:
            rot = bgr
        for d in decode(rot, symbols=[ZBarSymbol.QRCODE]):
            x, y, w, h = d.rect
            results.append((d.data.decode("utf-8"), (x, y, w, h)))
        if results:
            break
    return results


__all__ = ["detect_qr_positions"]
