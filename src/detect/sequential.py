from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from ..image_ops.qr import QRCodeMetadata, extract_qr_before_processing, parse_rocketbook_qr


@dataclass
class SequentialPageInfo:
    """Information about sequential pages."""
    page_number: Optional[int]
    date: Optional[str]
    notebook_id: Optional[str]
    is_sequential: bool
    page_order: List[int]  # Indices of pages in chronological order


def extract_date_from_text(text: str) -> Optional[str]:
    """
    Extract date from text content using regex patterns.
    
    Args:
        text: Text content to search for dates
        
    Returns:
        Date string in MM/DD/YYYY format, or None if not found
    """
    if not text:
        return None
    
    # Common date patterns
    date_patterns = [
        r"(\d{1,2})/(\d{1,2})/(\d{2,4})",  # MM/DD/YYYY or MM/DD/YY
        r"(\d{4})-(\d{1,2})-(\d{1,2})",    # YYYY-MM-DD
        r"(\d{1,2})-(\d{1,2})-(\d{2,4})",  # MM-DD-YYYY or MM-DD-YY
        r"(\d{1,2})\s+(\d{1,2}),\s+(\d{4})",  # Month DD, YYYY (e.g., "10 22, 2025")
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            if "/" in pattern:
                # MM/DD/YYYY format
                month, day, year = match.groups()
                if len(year) == 2:
                    year = "20" + year
                return f"{month}/{day}/{year}"
            elif "-" in pattern and len(match.group(1)) == 4:
                # YYYY-MM-DD format
                year, month, day = match.groups()
                return f"{month}/{day}/{year}"
            elif "," in pattern:
                # Month DD, YYYY format
                month, day, year = match.groups()
                return f"{month}/{day}/{year}"
            else:
                # MM-DD-YYYY format
                month, day, year = match.groups()
                if len(year) == 2:
                    year = "20" + year
                return f"{month}/{day}/{year}"
    
    return None


def detect_sequential_pages(
    images: List[Tuple],  # List of (image_path, bgr_image) tuples
    qr_metadata_list: Optional[List[List[QRCodeMetadata]]] = None
) -> SequentialPageInfo:
    """
    Detect if images are part of a sequential series and determine page order.
    
    Args:
        images: List of tuples (image_path, bgr_image) for each image
        qr_metadata_list: Optional list of QR metadata lists (one per image)
                         If not provided, will extract QR codes from images
        
    Returns:
        SequentialPageInfo with detected page information
    """
    if not images:
        return SequentialPageInfo(
            page_number=None,
            date=None,
            notebook_id=None,
            is_sequential=False,
            page_order=[]
        )
    
    # Extract QR codes if not provided
    if qr_metadata_list is None:
        qr_metadata_list = []
        for _, bgr in images:
            qr_metadata = extract_qr_before_processing(bgr)
            qr_metadata_list.append(qr_metadata)
    
    # Try to extract dates and page numbers from QR codes
    dates = []
    page_numbers = []
    notebook_ids = []
    
    for qr_list in qr_metadata_list:
        if qr_list:
            # Use first QR code from each image
            qr = qr_list[0]
            if qr.date:
                dates.append(qr.date)
            if qr.page_number is not None:
                page_numbers.append(qr.page_number)
            if qr.notebook_id:
                notebook_ids.append(qr.notebook_id)
    
    # Determine if sequential
    is_sequential = False
    page_order = list(range(len(images)))  # Default order
    
    # Check if we have page numbers that indicate sequence
    if page_numbers and len(page_numbers) == len(images):
        # Check if page numbers are sequential
        sorted_pages = sorted(page_numbers)
        is_sequential = all(
            sorted_pages[i] == sorted_pages[0] + i
            for i in range(len(sorted_pages))
        )
        
        if is_sequential:
            # Sort images by page number
            indexed = list(enumerate(page_numbers))
            indexed.sort(key=lambda x: x[1])
            page_order = [idx for idx, _ in indexed]
    
    # Check if we have consistent dates (same day)
    if dates and len(dates) == len(images):
        # Check if all dates are the same
        if len(set(dates)) == 1:
            is_sequential = True
    
    # Check if we have consistent notebook IDs
    if notebook_ids and len(notebook_ids) == len(images):
        # Check if all notebook IDs are the same
        if len(set(notebook_ids)) == 1:
            is_sequential = True
    
    # Determine common date (use most common date if available)
    common_date = None
    if dates:
        # Use the most common date
        from collections import Counter
        date_counts = Counter(dates)
        common_date = date_counts.most_common(1)[0][0] if date_counts else None
    
    # Determine common notebook ID
    common_notebook_id = None
    if notebook_ids:
        # Use the most common notebook ID
        from collections import Counter
        id_counts = Counter(notebook_ids)
        common_notebook_id = id_counts.most_common(1)[0][0] if id_counts else None
    
    return SequentialPageInfo(
        page_number=None,  # Page number is per-image, not global
        date=common_date,
        notebook_id=common_notebook_id,
        is_sequential=is_sequential,
        page_order=page_order
    )


def build_cumulative_context(
    texts: List[str],
    page_order: List[int]
) -> str:
    """
    Build cumulative context from sequential pages, maintaining chronological order.
    
    Args:
        texts: List of text content from each page (in original order)
        page_order: List of indices indicating chronological page order
        
    Returns:
        Combined text with cumulative context markers
    """
    if not texts:
        return ""
    
    # Reorder texts according to page order
    ordered_texts = [texts[idx] for idx in page_order if 0 <= idx < len(texts)]
    
    # Combine with context markers
    combined_parts = []
    for idx, text in enumerate(ordered_texts):
        if idx > 0:
            # Add separator between pages
            combined_parts.append("\n\n--- Page {} ---\n\n".format(idx + 1))
        combined_parts.append(text)
    
    return "\n".join(combined_parts)


def identify_session_themes(
    texts: List[str],
    min_occurrences: int = 2
) -> List[str]:
    """
    Identify recurring themes across pages that might indicate same-day session.
    
    Args:
        texts: List of text content from each page
        min_occurrences: Minimum number of pages a theme must appear in
        
    Returns:
        List of identified theme keywords
    """
    if not texts:
        return []
    
    # Simple keyword extraction (can be enhanced with NLP)
    import re
    from collections import Counter
    
    all_keywords = []
    for text in texts:
        if not text:
            continue
        
        # Extract capitalized words (potential names, projects, etc.)
        words = re.findall(r'\b[A-Z][a-z]+\b', text)
        all_keywords.extend(words.lower() if words else [])
        
        # Extract technical terms (acronyms, hyphenated terms)
        tech_terms = re.findall(r'\b[A-Z]{2,}\b', text)
        all_keywords.extend(tech_terms)
        
        # Extract common action words
        action_words = re.findall(r'\b(meeting|discussion|review|follow|up|schedule|plan)\b', text.lower())
        all_keywords.extend(action_words)
    
    # Count occurrences
    keyword_counts = Counter(all_keywords)
    
    # Find themes that appear in multiple pages
    themes = [
        keyword for keyword, count in keyword_counts.items()
        if count >= min_occurrences
    ]
    
    return sorted(themes)


__all__ = [
    "SequentialPageInfo",
    "extract_date_from_text",
    "detect_sequential_pages",
    "build_cumulative_context",
    "identify_session_themes",
]
