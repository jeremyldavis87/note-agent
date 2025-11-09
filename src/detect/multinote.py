from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np


@dataclass
class Region:
    bbox: Tuple[int, int, int, int]  # x, y, w, h
    position_label: str              # e.g., row_1_col_1
    note_color: Optional[str] = None  # detected note color (for sticky notes)


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


def _calculate_iou(bbox1: Tuple[int, int, int, int], bbox2: Tuple[int, int, int, int]) -> float:
    """
    Calculate Intersection over Union (IoU) of two bounding boxes.
    
    Args:
        bbox1: (x, y, w, h) of first bounding box
        bbox2: (x, y, w, h) of second bounding box
        
    Returns:
        IoU value between 0 and 1
    """
    x1, y1, w1, h1 = bbox1
    x2, y2, w2, h2 = bbox2
    
    # Calculate intersection
    xi1 = max(x1, x2)
    yi1 = max(y1, y2)
    xi2 = min(x1 + w1, x2 + w2)
    yi2 = min(y1 + h1, y2 + h2)
    
    if xi2 <= xi1 or yi2 <= yi1:
        return 0.0
    
    inter_area = (xi2 - xi1) * (yi2 - yi1)
    
    # Calculate union
    box1_area = w1 * h1
    box2_area = w2 * h2
    union_area = box1_area + box2_area - inter_area
    
    if union_area == 0:
        return 0.0
    
    return inter_area / union_area


def _filter_large_regions(
    regions: List[Region],
    image_shape: Tuple[int, int],
    max_width_ratio: float = 0.5,
    max_height_ratio: float = 0.5,
    max_area_ratio: float = 0.2,
) -> List[Region]:
    """
    Filter out regions that are too large relative to image dimensions.
    
    Args:
        regions: List of Region objects to filter
        image_shape: (height, width) of the image
        max_width_ratio: Maximum width as ratio of image width (default 0.5 = 50%)
        max_height_ratio: Maximum height as ratio of image height (default 0.5 = 50%)
        max_area_ratio: Maximum area as ratio of image area (default 0.2 = 20%)
        
    Returns:
        Filtered list of regions
    """
    h, w = image_shape
    filtered = []
    
    for region in regions:
        x, y, w_box, h_box = region.bbox
        
        # Check width and height ratios
        width_ratio = w_box / w
        height_ratio = h_box / h
        
        # Check area ratio
        region_area = w_box * h_box
        image_area = w * h
        area_ratio = region_area / image_area
        
        # Filter out regions that are too large
        if (
            width_ratio > max_width_ratio
            or height_ratio > max_height_ratio
            or area_ratio > max_area_ratio
        ):
            continue
        
        filtered.append(region)
    
    return filtered


def _is_contained(small_bbox: Tuple[int, int, int, int], large_bbox: Tuple[int, int, int, int]) -> bool:
    """Check if small_bbox is completely contained within large_bbox."""
    sx, sy, sw, sh = small_bbox
    lx, ly, lw, lh = large_bbox
    
    return (
        sx >= lx
        and sy >= ly
        and (sx + sw) <= (lx + lw)
        and (sy + sh) <= (ly + lh)
    )


def _assign_unique_position_labels(regions: List[Region], image_shape: Tuple[int, int]) -> List[Region]:
    """
    Assign unique position labels to regions based on spatial ordering.
    
    This ensures no duplicate position labels by:
    1. Sorting regions spatially (top to bottom, left to right)
    2. Clustering regions into grid cells
    3. Assigning unique labels within each cell
    
    Args:
        regions: List of Region objects with bounding boxes
        image_shape: (height, width) of the image
        
    Returns:
        List of regions with unique position labels assigned
    """
    if not regions:
        return regions
    
    h, w = image_shape
    
    # Sort regions by position (top to bottom, left to right)
    sorted_regions = sorted(regions, key=lambda r: (r.bbox[1], r.bbox[0]))
    
    # Calculate grid cell size
    cell_h = h / 3
    cell_w = w / 3
    
    # Track which positions are already assigned
    assigned_positions: set[str] = set()
    
    # Assign positions based on spatial order, ensuring uniqueness
    for region in sorted_regions:
        x, y, w_box, h_box = region.bbox
        center_x = x + w_box // 2
        center_y = y + h_box // 2
        
        # Calculate preferred grid cell
        row = int(center_y / cell_h) + 1
        col = int(center_x / cell_w) + 1
        row = max(1, min(3, row))
        col = max(1, min(3, col))
        
        # Check if preferred position is available
        preferred_label = f"row_{row}_col_{col}"
        if preferred_label not in assigned_positions:
            region.position_label = preferred_label
            assigned_positions.add(preferred_label)
        else:
            # Find nearest available position
            # Try positions in order: same row adjacent cols, then adjacent rows
            found = False
            for dr in [0, -1, 1, -2, 2]:
                for dc in [0, -1, 1, -2, 2]:
                    if dr == 0 and dc == 0:
                        continue  # Already tried preferred
                    new_row = row + dr
                    new_col = col + dc
                    if 1 <= new_row <= 3 and 1 <= new_col <= 3:
                        candidate_label = f"row_{new_row}_col_{new_col}"
                        if candidate_label not in assigned_positions:
                            region.position_label = candidate_label
                            assigned_positions.add(candidate_label)
                            found = True
                            break
                if found:
                    break
            
            # If still no position found (shouldn't happen with 9 or fewer regions)
            if not found:
                # Fallback: use preferred position with index
                for idx in range(1, 10):
                    fallback_label = f"{preferred_label}_alt{idx}"
                    if fallback_label not in assigned_positions:
                        region.position_label = fallback_label
                        assigned_positions.add(fallback_label)
                        break
    
    return sorted_regions


def _merge_overlapping_regions(regions: List[Region], iou_threshold: float = 0.5) -> List[Region]:
    """
    Merge overlapping regions based on IoU threshold.
    
    Prefers regions that are closest to typical sticky note size (around 5-7% of image area).
    
    Args:
        regions: List of Region objects
        iou_threshold: IoU threshold above which regions are merged
        
    Returns:
        List of merged/deduplicated regions
    """
    if len(regions) <= 1:
        return regions
    
    # Calculate expected note size
    # For a 3x3 grid of 820x820 notes in a ~3000x2700 image, each note is ~8.2% of image area
    areas = [r.bbox[2] * r.bbox[3] for r in regions]
    if not areas:
        return regions
    
    # Target area for sticky notes (820x820 = 672,400 pixels)
    target_area = 672400  # 820 * 820
    
    merged = []
    used = set()
    
    for i, region1 in enumerate(regions):
        if i in used:
            continue
        
        # Find all regions that overlap with this one
        overlapping = [region1]
        for j, region2 in enumerate(regions[i+1:], start=i+1):
            if j in used:
                continue
            
            iou = _calculate_iou(region1.bbox, region2.bbox)
            if iou > iou_threshold:
                overlapping.append(region2)
                used.add(j)
        
        # Merge overlapping regions
        if len(overlapping) > 1:
            # Prefer region closest to target note size
            # This favors edge-detected regions with borders over smaller text-only regions
            overlapping.sort(
                key=lambda r: abs((r.bbox[2] * r.bbox[3]) - target_area)
            )
            merged.append(overlapping[0])
        else:
            merged.append(region1)
        used.add(i)
    
    return merged


def _remove_encompassed_regions(regions: List[Region]) -> List[Region]:
    """
    Remove regions that are completely contained within other regions.
    
    A region is considered encompassed if it is completely inside another region
    (with some small margin for error).
    
    Args:
        regions: List of Region objects
        
    Returns:
        List of regions with encompassed ones removed
    """
    if len(regions) <= 1:
        return regions
    
    filtered = []
    
    for i, region1 in enumerate(regions):
        is_encompassed = False
        x1, y1, w1, h1 = region1.bbox
        area1 = w1 * h1
        
        for j, region2 in enumerate(regions):
            if i == j:
                continue
            
            x2, y2, w2, h2 = region2.bbox
            area2 = w2 * h2
            
            # Only check if region1 is significantly smaller than region2
            if area1 < area2 * 0.7:  # region1 is at least 30% smaller
                # Check if region1 is contained within region2 (with 10 pixel margin)
                margin = 10
                if (x1 >= x2 - margin and 
                    y1 >= y2 - margin and 
                    x1 + w1 <= x2 + w2 + margin and 
                    y1 + h1 <= y2 + h2 + margin):
                    is_encompassed = True
                    break
        
        if not is_encompassed:
            filtered.append(region1)
    
    return filtered


def detect_notes_by_text_regions(bgr: np.ndarray) -> List[Region]:
    """
    Detect white/light notes by finding text-rich regions.
    
    This approach works for white notes where edge detection fails because
    there are no visible edges. Instead, we detect dark text pixels and
    cluster them into note regions.
    
    Args:
        bgr: BGR image potentially containing white notes
        
    Returns:
        List of detected note regions with bounding boxes
    """
    h, w = bgr.shape[:2]
    
    # Convert to grayscale
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    
    # Apply Gaussian blur
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Use adaptive threshold to find dark text on light background
    # For white notes, text is dark, background is light
    adaptive_thresh = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 10
    )
    
    # Find connected components (text regions)
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(adaptive_thresh, connectivity=8)
    
    # Group nearby text components into note regions
    # Use DBSCAN-like clustering or simple proximity grouping
    text_regions = []
    min_text_area = 100  # Minimum pixels for a text component
    
    for i in range(1, num_labels):  # Skip background (label 0)
        x, y, w_comp, h_comp, area = stats[i]
        if area < min_text_area:
            continue
        
        # Check if this is likely text (narrow and tall, or wide and short)
        aspect = max(w_comp, h_comp) / max(min(w_comp, h_comp), 1)
        if aspect > 10:  # Too elongated, likely a line, not a note
            continue
        
        text_regions.append((x, y, w_comp, h_comp, area))
    
    if not text_regions:
        return []
    
    # Cluster nearby text regions into notes
    # Simple approach: group text regions that are close together
    note_regions = []
    used = set()
    
    for i, (x1, y1, w1, h1, area1) in enumerate(text_regions):
        if i in used:
            continue
        
        # Find all nearby text regions
        cluster = [(x1, y1, w1, h1)]
        used.add(i)
        
        for j, (x2, y2, w2, h2, area2) in enumerate(text_regions[i+1:], start=i+1):
            if j in used:
                continue
            
            # Calculate distance between centers
            center1_x = x1 + w1 // 2
            center1_y = y1 + h1 // 2
            center2_x = x2 + w2 // 2
            center2_y = y2 + h2 // 2
            
            dist = np.sqrt((center1_x - center2_x)**2 + (center1_y - center2_y)**2)
            max_dist = max(w1, h1, w2, h2) * 2  # Allow 2x the size as max distance
            
            if dist < max_dist:
                cluster.append((x2, y2, w2, h2))
                used.add(j)
        
        # Calculate bounding box for cluster
        min_x = min(x for x, _, _, _ in cluster)
        min_y = min(y for _, y, _, _ in cluster)
        max_x = max(x + w for x, _, w, _ in cluster)
        max_y = max(y + h for _, y, _, h in cluster)
        
        w_box = max_x - min_x
        h_box = max_y - min_y
        
        # Filter by size
        if w_box < 100 or h_box < 100:  # Too small
            continue
        
        width_ratio = w_box / w
        height_ratio = h_box / h
        area_ratio = (w_box * h_box) / (w * h)
        
        # Must be reasonable size for a note
        if width_ratio > 0.5 or height_ratio > 0.5 or area_ratio > 0.15:
            continue
        
        # Check aspect ratio
        aspect_ratio = w_box / max(h_box, 1)
        if aspect_ratio < 0.3 or aspect_ratio > 3.0:
            continue
        
        # Calculate position label
        row = int((min_y + h_box // 2) / (h / 3)) + 1
        col = int((min_x + w_box // 2) / (w / 3)) + 1
        row = max(1, min(3, row))
        col = max(1, min(3, col))
        position_label = f"row_{row}_col_{col}"
        
        # Extract region to detect color
        region_img = bgr[min_y:min_y+h_box, min_x:min_x+w_box]
        if region_img.size == 0:
            continue
        
        note_color = detect_note_color(region_img)
        
        note_regions.append(Region(
            bbox=(min_x, min_y, w_box, h_box),
            position_label=position_label,
            note_color=note_color
        ))
    
    return note_regions


def detect_notes_by_edges(bgr: np.ndarray) -> List[Region]:
    """
    Detect sticky notes by detecting their edges/borders, works for arbitrary layouts.
    
    This method detects notes by finding rectangular edges, regardless of color.
    Works for white notes, colored notes, and arbitrary layouts.
    
    Args:
        bgr: BGR image potentially containing multiple sticky notes
        
    Returns:
        List of detected note regions with bounding boxes
    """
    h, w = bgr.shape[:2]
    
    # Convert to grayscale
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    
    # Apply Gaussian blur to reduce noise
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Apply adaptive thresholding to separate notes from background
    # Use smaller blockSize for better detection of individual notes
    adaptive_thresh = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 9, 2
    )
    
    # Also try Canny edge detection with lower thresholds for better white note detection
    edges_canny = cv2.Canny(blurred, 30, 100, apertureSize=3)
    
    # Combine edge information
    combined_edges = cv2.bitwise_or(adaptive_thresh, edges_canny)
    
    # Apply morphological operations to connect nearby edges
    # Use larger kernel for better edge connection
    kernel = np.ones((5, 5), np.uint8)
    # Close first to connect broken edges, then dilate to strengthen
    combined_edges = cv2.morphologyEx(combined_edges, cv2.MORPH_CLOSE, kernel)
    combined_edges = cv2.dilate(combined_edges, kernel, iterations=1)
    combined_edges = cv2.morphologyEx(combined_edges, cv2.MORPH_OPEN, kernel)
    
    # Find contours - use RETR_TREE to get hierarchy and filter out parent contours
    contours, hierarchy = cv2.findContours(combined_edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    
    # Filter out parent contours (those with children) - they're usually the entire page
    # Keep only leaf contours (no children) or simple contours
    if hierarchy is not None:
        filtered_contours = []
        for idx, contour in enumerate(contours):
            # hierarchy format: [Next, Previous, First_Child, Parent]
            # If it has children (First_Child != -1), it's likely a parent contour (whole page)
            # We want leaf contours (no children) or contours with very specific parent-child relationships
            child_idx = hierarchy[0][idx][2]
            parent_idx = hierarchy[0][idx][3]
            
            # Skip if it has children (parent contour) unless it's reasonable size
            # Also skip if it's the entire image (parent = -1 but huge)
            if child_idx != -1:
                # Has children - likely a parent, but check if it's reasonable
                x, y, w_box, h_box = cv2.boundingRect(contour)
                if (w_box / w > 0.5) or (h_box / h > 0.5):
                    continue  # Too large to be a note
            filtered_contours.append(contour)
        contours = filtered_contours
    
    regions = []
    min_area = (w * h) / 200  # Minimum area threshold (0.5% of image)
    max_area = (w * h) * 0.25  # Maximum area threshold (25% of image)
    
    for contour in contours:
        # Get bounding rectangle FIRST to check dimensions early
        x, y, w_box, h_box = cv2.boundingRect(contour)
        
        # CRITICAL: Filter by bounding box dimensions BEFORE any other processing
        # This prevents huge boxes from even being considered
        width_ratio = w_box / w
        height_ratio = h_box / h
        bbox_area_ratio = (w_box * h_box) / (w * h)
        
        # Aggressive filtering: reject if width > 50% OR height > 50% OR area > 15%
        if width_ratio > 0.5 or height_ratio > 0.5 or bbox_area_ratio > 0.15:
            continue
        
        # Check minimum size
        if w_box < 50 or h_box < 50:
            continue
        
        area = cv2.contourArea(contour)
        
        # Filter by contour area (more permissive than bbox area)
        if area < min_area or area > max_area:
            continue
        
        # Approximate contour to polygon (more flexible for white notes)
        epsilon = 0.03 * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon, True)
        
        # Check if it's roughly rectangular (4-6 vertices)
        if len(approx) < 4 or len(approx) > 6:
            continue
        
        # Check convexity, but also check if bounding box area is close to contour area
        # (allows slightly non-convex if it's close to rectangular)
        bbox_area = w_box * h_box
        contour_area = cv2.contourArea(contour)
        area_ratio = contour_area / max(bbox_area, 1)
        
        # If contour is close to rectangular (area ratio > 0.7), allow non-convex
        if not cv2.isContourConvex(approx) and area_ratio < 0.7:
            continue
        
        # Filter by aspect ratio (notes are roughly square/rectangular)
        aspect_ratio = w_box / max(h_box, 1)
        if aspect_ratio < 0.4 or aspect_ratio > 2.5:
            continue
        
        # Extract region to detect color
        region_img = bgr[y:y+h_box, x:x+w_box]
        if region_img.size == 0:
            continue
        
        # Detect note color
        note_color = detect_note_color(region_img)
        
        # Expand bounding box to include the colored border
        # Edge detection finds the inner boundary (content area), so expand outward
        # Calculate padding to target final size of ~820x820 pixels
        # Average detected content is ~670x680, so we need ~75 pixels per side
        border_padding = 72
        x_expanded = max(0, x - border_padding)
        y_expanded = max(0, y - border_padding)
        w_expanded = min(w - x_expanded, w_box + 2 * border_padding)
        h_expanded = min(h - y_expanded, h_box + 2 * border_padding)
        
        # Calculate position label based on grid position (for compatibility)
        row = int((y_expanded + h_expanded // 2) / (h / 3)) + 1
        col = int((x_expanded + w_expanded // 2) / (w / 3)) + 1
        row = max(1, min(3, row))
        col = max(1, min(3, col))
        position_label = f"row_{row}_col_{col}"
        
        regions.append(Region(
            bbox=(x_expanded, y_expanded, w_expanded, h_expanded),
            position_label=position_label,
            note_color=note_color
        ))
    
    # Filter out regions that are too large relative to image dimensions
    regions = _filter_large_regions(regions, (h, w))
    
    # Sort regions by position (top to bottom, left to right)
    regions.sort(key=lambda r: (r.bbox[1], r.bbox[0]))
    
    return regions


def detect_note_color(bgr_region: np.ndarray, border_pixels: Optional[np.ndarray] = None) -> Optional[str]:
    """
    Detect note color by analyzing border pixels or dominant color.
    
    Args:
        bgr_region: Cropped BGR image of a note region
        border_pixels: Optional pre-extracted border pixels (for efficiency)
        
    Returns:
        Color name (orange, green, blue, yellow, pink, purple, red) or None
    """
    h, w = bgr_region.shape[:2]
    
    # Extract border pixels if not provided
    if border_pixels is None:
        # Sample border pixels (top, bottom, left, right edges)
        border_width = max(3, min(w, h) // 20)  # Adaptive border width
        top_border = bgr_region[0:border_width, :].reshape(-1, 3)
        bottom_border = bgr_region[h-border_width:h, :].reshape(-1, 3)
        left_border = bgr_region[:, 0:border_width].reshape(-1, 3)
        right_border = bgr_region[:, w-border_width:w].reshape(-1, 3)
        border_pixels = np.vstack([top_border, bottom_border, left_border, right_border])
    
    # Calculate average color of border pixels
    avg_b, avg_g, avg_r = border_pixels.mean(axis=0)
    r, g, b = int(avg_r), int(avg_g), int(avg_b)
    
    # Convert to HSV for better color discrimination
    # Create a single pixel image to convert to HSV
    pixel_bgr = np.uint8([[[b, g, r]]])
    pixel_hsv = cv2.cvtColor(pixel_bgr, cv2.COLOR_BGR2HSV)[0][0]
    h, s, v = pixel_hsv[0], pixel_hsv[1], pixel_hsv[2]
    
    # Determine color from RGB and HSV values
    # Check for yellow/cream first (common light colors)
    # Yellow: high red, high green, low blue, and hue in yellow range (15-30)
    if r > 150 and g > 150 and b < 120:
        # Use HSV to distinguish yellow from orange
        # Yellow hue is typically 15-30, Orange hue is typically 5-15
        if 15 <= h <= 30:
            return "yellow"
        # If it's in the orange range but very light, it might be cream/yellow
        elif 5 <= h <= 15 and v > 200:
            # Very light orange-like color is likely cream/yellow
            return "yellow"
    
    # Orange: distinct orange hue (5-15), medium saturation, not too light
    # Orange should have: high red, medium green (lower than yellow), low blue
    # And hue in orange range with decent saturation
    if r > 150 and 80 <= g <= 180 and b < 120:
        if 5 <= h <= 15 and s > 80:
            # Distinct orange with good saturation
            return "orange"
        elif 5 <= h <= 15 and v < 200:
            # Darker orange-like color
            return "orange"
    
    # Green: low red, high green, low blue
    if r < 100 and g > 150 and b < 100:
        return "green"
    # Blue: low red, medium green, high blue
    elif r < 100 and g < 150 and b > 150:
        return "blue"
    # Pink: high red, medium-high green, medium-high blue
    elif r > 180 and g > 100 and g < 180 and b > 100 and b < 180:
        return "pink"
    # Purple: medium red, low-medium green, high blue
    elif r > 100 and r < 180 and g < 120 and b > 150:
        return "purple"
    # Red: very high red, low green, low blue
    elif r > 200 and g < 80 and b < 80:
        return "red"
    
    return None


def detect_sticky_notes(bgr: np.ndarray) -> List[Region]:
    """
    Detect individual sticky notes using hybrid detection approach.
    
    Combines:
    1. Edge-based detection (works for all note types, including white notes)
    2. Color-based detection (for notes with colored borders)
    
    This hybrid approach handles arbitrary layouts and various note colors.
    
    Args:
        bgr: BGR image potentially containing multiple sticky notes
        
    Returns:
        List of detected note regions with bounding boxes and colors
    """
    h, w = bgr.shape[:2]
    
    # Strategy 1: Edge-based detection (works for notes with visible borders)
    edge_regions = detect_notes_by_edges(bgr)
    
    # Strategy 2: Text-based detection (for white/light notes where edges fail)
    text_regions = detect_notes_by_text_regions(bgr)
    
    # Strategy 3: Color-based detection (for colored borders)
    color_regions = _detect_sticky_notes_by_color(bgr)
    
    # Combine and merge results
    all_regions = edge_regions + text_regions + color_regions
    
    # Filter out obviously oversized regions BEFORE merging to prevent contamination
    # Use more permissive thresholds than final filtering
    all_regions = _filter_large_regions(all_regions, (h, w), max_width_ratio=0.45, max_height_ratio=0.50, max_area_ratio=0.13)
    
    # Deduplicate overlapping regions
    merged_regions = _merge_overlapping_regions(all_regions, iou_threshold=0.5)
    
    # Remove regions that are completely encompassed by other regions
    merged_regions = _remove_encompassed_regions(merged_regions)
    
    # Filter out any remaining large regions (> 40% of image width or height)
    merged_regions = _filter_large_regions(merged_regions, (h, w), max_width_ratio=0.40, max_height_ratio=0.40, max_area_ratio=0.10)
    
    # Filter out very small regions (likely noise or partial detections)
    # Calculate median area of remaining regions
    if len(merged_regions) > 0:
        areas = [r.bbox[2] * r.bbox[3] for r in merged_regions]
        median_area = np.median(areas)
        # Remove regions that are less than 20% of median area
        merged_regions = [r for r in merged_regions if r.bbox[2] * r.bbox[3] >= median_area * 0.2]
    
    # If we found some regions but not many, check if grid pattern is expected
    # and supplement with grid split if needed
    if 0 < len(merged_regions) < 6:
        # Check if detected regions suggest a grid pattern
        grid_regions = split_three_by_three(bgr)
        # Add grid regions that don't overlap significantly with detected regions
        for grid_region in grid_regions:
            overlaps = False
            for detected in merged_regions:
                iou = _calculate_iou(grid_region.bbox, detected.bbox)
                if iou > 0.3:  # If significant overlap, skip
                    overlaps = True
                    break
            if not overlaps:
                merged_regions.append(grid_region)
        
        # Merge again after adding grid regions
        merged_regions = _merge_overlapping_regions(merged_regions, iou_threshold=0.3)
        
        # Remove encompassed regions again
        merged_regions = _remove_encompassed_regions(merged_regions)
        
        # Filter again after grid supplementation
        merged_regions = _filter_large_regions(merged_regions, (h, w), max_width_ratio=0.40, max_height_ratio=0.40, max_area_ratio=0.10)
    
    # If we didn't find any notes, fall back to grid split
    if len(merged_regions) == 0:
        return split_three_by_three(bgr)
    
    # Final filter to remove any regions that are clearly too large
    merged_regions = _filter_large_regions(merged_regions, (h, w), max_width_ratio=0.40, max_height_ratio=0.40, max_area_ratio=0.10)
    
    # Assign unique position labels based on spatial ordering
    merged_regions = _assign_unique_position_labels(merged_regions, (h, w))
    
    # Sort regions by position (top to bottom, left to right)
    merged_regions.sort(key=lambda r: (r.bbox[1], r.bbox[0]))
    
    return merged_regions


def _detect_sticky_notes_by_color(bgr: np.ndarray) -> List[Region]:
    """
    Detect sticky notes with colored borders using HSV color filtering.
    This is a helper function used by detect_sticky_notes().
    
    Args:
        bgr: BGR image potentially containing multiple sticky notes
        
    Returns:
        List of detected note regions with colored borders
    """
    h, w = bgr.shape[:2]
    
    # Convert to HSV for better color detection
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    
    # Create mask for colored borders (saturated colors, excluding white/gray)
    # Define color ranges for common sticky note colors with expanded/permissive ranges
    color_masks = []
    
    # Orange: HSV range for orange (expanded saturation range)
    orange_lower = np.array([5, 50, 80])  # Lower saturation threshold
    orange_upper = np.array([25, 255, 255])
    color_masks.append(("orange", cv2.inRange(hsv, orange_lower, orange_upper)))
    
    # Green: HSV range for green (expanded saturation range)
    green_lower = np.array([35, 50, 80])  # Lower saturation threshold
    green_upper = np.array([85, 255, 255])  # Expanded hue range
    color_masks.append(("green", cv2.inRange(hsv, green_lower, green_upper)))
    
    # Blue: HSV range for blue (expanded saturation range)
    blue_lower = np.array([95, 50, 80])  # Lower saturation threshold
    blue_upper = np.array([135, 255, 255])  # Expanded hue range
    color_masks.append(("blue", cv2.inRange(hsv, blue_lower, blue_upper)))
    
    # Yellow: HSV range for yellow (expanded saturation range)
    yellow_lower = np.array([15, 50, 80])  # Lower saturation threshold
    yellow_upper = np.array([35, 255, 255])  # Expanded hue range
    color_masks.append(("yellow", cv2.inRange(hsv, yellow_lower, yellow_upper)))
    
    # Pink: HSV range for pink/magenta (wraps around hue)
    # Pink wraps around hue 0-10 and 160-180
    pink_lower = np.array([160, 50, 80])  # Lower saturation threshold
    pink_upper = np.array([180, 255, 255])
    pink_mask1 = cv2.inRange(hsv, pink_lower, pink_upper)
    # Also try lower hue range for pink (0-10 degrees)
    pink_lower2 = np.array([0, 50, 80])
    pink_upper2 = np.array([10, 255, 255])
    pink_mask2 = cv2.inRange(hsv, pink_lower2, pink_upper2)
    # Combine both pink ranges
    pink_mask = cv2.bitwise_or(pink_mask1, pink_mask2)
    color_masks.append(("pink", pink_mask))
    
    # Combine all color masks
    combined_mask = np.zeros((h, w), dtype=np.uint8)
    for color_name, mask in color_masks:
        combined_mask = cv2.bitwise_or(combined_mask, mask)
    
    # Apply morphological operations to clean up the mask
    kernel = np.ones((5, 5), np.uint8)  # Larger kernel for better connectivity
    combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_CLOSE, kernel)
    combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_OPEN, kernel)
    # Dilate to connect nearby color regions
    combined_mask = cv2.dilate(combined_mask, kernel, iterations=2)
    
    # Find contours - use RETR_TREE to filter out parent contours
    contours, hierarchy = cv2.findContours(combined_mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    
    # Filter out parent contours (those with children) - they're usually too large
    if hierarchy is not None:
        filtered_contours = []
        for idx, contour in enumerate(contours):
            child_idx = hierarchy[0][idx][2]
            if child_idx != -1:
                # Has children - check if reasonable size
                x, y, w_box, h_box = cv2.boundingRect(contour)
                if (w_box / w > 0.5) or (h_box / h > 0.5):
                    continue  # Too large
            filtered_contours.append(contour)
        contours = filtered_contours
    
    regions = []
    min_area = (w * h) / 200  # Minimum area threshold (0.5% of image - more permissive)
    max_area = (w * h) * 0.25  # Maximum area threshold (25% of image)
    
    for idx, contour in enumerate(contours):
        # Get bounding box FIRST to check dimensions early
        x, y, w_box, h_box = cv2.boundingRect(contour)
        
        # CRITICAL: Filter by bounding box dimensions BEFORE any other processing
        width_ratio = w_box / w
        height_ratio = h_box / h
        bbox_area_ratio = (w_box * h_box) / (w * h)
        
        # Aggressive filtering: reject if width > 50% OR height > 50% OR area > 15%
        if width_ratio > 0.5 or height_ratio > 0.5 or bbox_area_ratio > 0.15:
            continue
        
        area = cv2.contourArea(contour)
        
        # Filter by area
        if area < min_area or area > max_area:
            continue
        
        # Ensure reasonable aspect ratio (notes are roughly square/rectangular)
        aspect_ratio = w_box / max(h_box, 1)
        if aspect_ratio < 0.4 or aspect_ratio > 2.5:  # More permissive aspect ratio
            continue
        
        # Extract region to detect color
        region_img = bgr[y:y+h_box, x:x+w_box]
        if region_img.size == 0:
            continue
        
        # Detect note color from border
        note_color = detect_note_color(region_img)
        
        # Calculate grid position (if we can determine it)
        # For now, use a simple row/col based on position
        row = int((y + h_box // 2) / (h / 3)) + 1
        col = int((x + w_box // 2) / (w / 3)) + 1
        row = max(1, min(3, row))
        col = max(1, min(3, col))
        position_label = f"row_{row}_col_{col}"
        
        regions.append(Region(
            bbox=(x, y, w_box, h_box),
            position_label=position_label,
            note_color=note_color
        ))
    
    # Filter out regions that are too large relative to image dimensions
    regions = _filter_large_regions(regions, (h, w))
    
    return regions


def detect_page_sections(bgr: np.ndarray) -> List[Region]:
    """
    Detect logical sections in a notebook page using horizontal line detection and whitespace analysis.
    
    Args:
        bgr: BGR image of a notebook page
        
    Returns:
        List of detected section regions
    """
    h, w = bgr.shape[:2]
    
    # Convert to grayscale
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    
    # Apply preprocessing
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    
    # Detect horizontal lines using HoughLines
    # Use Canny edge detection first
    edges = cv2.Canny(denoised, 50, 150, apertureSize=3)
    
    # Detect horizontal lines (separators)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=int(w * 0.3))
    
    section_boundaries = [0]  # Start with top of page
    
    if lines is not None:
        for line in lines:
            rho, theta = line[0]
            # Only consider near-horizontal lines (within 10 degrees)
            if abs(theta - np.pi / 2) < np.pi / 18:  # ~10 degrees
                y_pos = int(rho)
                if 0 < y_pos < h:
                    section_boundaries.append(y_pos)
    
    section_boundaries.append(h)  # End with bottom of page
    section_boundaries = sorted(set(section_boundaries))
    
    # Merge boundaries that are too close (< 50 pixels apart)
    merged_boundaries = [section_boundaries[0]]
    for boundary in section_boundaries[1:]:
        if boundary - merged_boundaries[-1] > 50:
            merged_boundaries.append(boundary)
        else:
            # Merge with previous boundary
            merged_boundaries[-1] = boundary
    
    # Create regions from boundaries
    regions = []
    for idx, (y_start, y_end) in enumerate(zip(merged_boundaries[:-1], merged_boundaries[1:])):
        if y_end - y_start < 30:  # Skip very small sections
            continue
        
        regions.append(Region(
            bbox=(0, y_start, w, y_end - y_start),
            position_label=f"section_{idx + 1}"
        ))
    
    # If no sections detected, return full page as single region
    if len(regions) == 0:
        return [Region(bbox=(0, 0, w, h), position_label="section_1")]
    
    return regions


def detect_regions(image: np.ndarray, force_single: bool = False) -> List[Region]:
    """
    Detect regions (notes or sections) in an image.
    
    Uses intelligent detection:
    - For sticky notes: contour detection with color-based filtering
    - For notebook pages: section boundary detection
    
    Falls back to simple grid split if detection fails.
    
    Args:
        image: BGR image
        force_single: If True, return single region covering entire image
        
    Returns:
        List of detected regions
    """
    if force_single:
        h, w = image.shape[:2]
        return [Region(bbox=(0, 0, w, h), position_label="row_1_col_1")]
    
    h, w = image.shape[:2]
    
    # Try to detect sticky notes first (for grid layouts)
    sticky_notes = detect_sticky_notes(image)
    
    # If we detected multiple regions (more than 1), use sticky note detection
    if len(sticky_notes) > 1:
        return sticky_notes
    
    # Otherwise, try section detection for notebook pages
    sections = detect_page_sections(image)
    
    # If we got multiple sections, use those
    if len(sections) > 1:
        return sections
    
    # Fallback to simple 3x3 grid split
    return split_three_by_three(image)


__all__ = [
    "Region",
    "detect_regions",
    "detect_sticky_notes",
    "detect_page_sections",
    "detect_note_color",
    "detect_notes_by_edges",
    "detect_notes_by_text_regions",
    "_merge_overlapping_regions",
    "_calculate_iou",
    "_filter_large_regions",
    "_assign_unique_position_labels",
]
