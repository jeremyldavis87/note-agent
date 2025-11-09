#!/usr/bin/env python3
"""Test script for note detection improvements."""
import cv2
import sys
from pathlib import Path
from src.detect.multinote import detect_sticky_notes, _filter_large_regions

def test_detection(image_path: str):
    """Test detection on an image and print results."""
    print(f"Testing detection on: {image_path}")
    
    # Load image
    bgr = cv2.imread(image_path)
    if bgr is None:
        print(f"Error: Could not load image {image_path}")
        return
    
    h, w = bgr.shape[:2]
    print(f"Image size: {w}x{h} pixels")
    
    # Run detection
    regions = detect_sticky_notes(bgr)
    
    print(f"\nDetected {len(regions)} regions:")
    print("-" * 80)
    
    for idx, region in enumerate(regions, 1):
        x, y, w_box, h_box = region.bbox
        width_ratio = w_box / w
        height_ratio = h_box / h
        area_ratio = (w_box * h_box) / (w * h)
        
        print(f"Region {idx}:")
        print(f"  Position: {region.position_label}")
        print(f"  Bbox: ({x}, {y}, {w_box}, {h_box})")
        print(f"  Size ratios: width={width_ratio:.2%}, height={height_ratio:.2%}, area={area_ratio:.2%}")
        print(f"  Color: {region.note_color}")
        
        # Check if region is too large
        if width_ratio > 0.5 or height_ratio > 0.5 or area_ratio > 0.2:
            print(f"  ⚠️  WARNING: Region is too large!")
        print()
    
    # Check for large regions
    large_regions = [r for r in regions if (r.bbox[2] / w > 0.5 or r.bbox[3] / h > 0.5 or (r.bbox[2] * r.bbox[3]) / (w * h) > 0.2)]
    if large_regions:
        print(f"⚠️  Found {len(large_regions)} regions that are too large!")
        for r in large_regions:
            print(f"  - {r.position_label}: {r.bbox}")
    else:
        print("✓ No overly large regions detected")
    
    # Check for expected count (9 for 3x3 grid)
    if len(regions) == 9:
        print("✓ Detected all 9 notes!")
    elif len(regions) < 9:
        print(f"⚠️  Only detected {len(regions)} notes (expected 9)")
    else:
        print(f"⚠️  Detected {len(regions)} notes (expected 9)")
    
    # Check for row_3_col_2 specifically
    row_3_col_2 = [r for r in regions if r.position_label == "row_3_col_2"]
    if row_3_col_2:
        print("✓ Found row_3_col_2 note!")
    else:
        print("⚠️  Missing row_3_col_2 note")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_detection.py <image_path>")
        sys.exit(1)
    
    image_path = sys.argv[1]
    test_detection(image_path)

