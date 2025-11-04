"""Organizational hierarchy dictionary management for agent context."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ..logging_setup import setup_logging
import logging
from .utils import _load_context_file

logger = logging.getLogger(__name__)


def _validate_org_hierarchy(data: Any) -> bool:
    """
    Validate that the org hierarchy data has the correct structure.
    
    Args:
        data: The loaded JSON data
        
    Returns:
        True if valid, False otherwise
    """
    if not isinstance(data, dict):
        return False
    return True


def load_org_hierarchy() -> Dict:
    """
    Load organizational hierarchy from agent-context/org-hierarchy.json.
    
    Returns:
        Dictionary containing organizational hierarchy structure.
        Returns empty dict if file is missing or malformed.
    """
    return _load_context_file(
        "org-hierarchy.json",
        validate_func=_validate_org_hierarchy,
        description="organizational hierarchy"
    )


def _flatten_hierarchy(hierarchy: Dict, people_list: List[Dict]) -> None:
    """
    Recursively flatten the organizational hierarchy into a flat list of people.
    
    Args:
        hierarchy: The hierarchy dictionary (can be CEO or any person node)
        people_list: List to append people entries to
    """
    if not isinstance(hierarchy, dict):
        return
    
    # If this is a person node (has name and title)
    if "name" in hierarchy and "title" in hierarchy:
        people_list.append({
            "name": hierarchy["name"],
            "title": hierarchy.get("title", ""),
            "employee_id": hierarchy.get("employee_id"),
        })
    
    # Recursively process direct_reports
    if "direct_reports" in hierarchy and isinstance(hierarchy["direct_reports"], list):
        for report in hierarchy["direct_reports"]:
            _flatten_hierarchy(report, people_list)


def build_people_index(hierarchy: Dict) -> Dict[str, List[Dict]]:
    """
    Build a searchable index of people from the organizational hierarchy.
    
    Args:
        hierarchy: The loaded organizational hierarchy dictionary
        
    Returns:
        Dictionary with keys:
            - "by_name": List of all people indexed by name
            - "by_title": Dictionary mapping titles to lists of people
            - "all_people": List of all people with name, title, employee_id
    """
    people_list: List[Dict] = []
    
    # Start from CEO if present
    if "ceo" in hierarchy:
        _flatten_hierarchy(hierarchy["ceo"], people_list)
    
    # Build name and title indexes
    by_name: Dict[str, List[Dict]] = {}
    by_title: Dict[str, List[Dict]] = {}
    
    for person in people_list:
        name = person["name"]
        title = person.get("title", "")
        
        # Index by name
        if name not in by_name:
            by_name[name] = []
        by_name[name].append(person)
        
        # Index by title
        if title:
            if title not in by_title:
                by_title[title] = []
            by_title[title].append(person)
    
    return {
        "by_name": by_name,
        "by_title": by_title,
        "all_people": people_list,
    }


def search_people_by_name(
    text: str,
    people_index: Dict[str, List[Dict]],
    fuzzy: bool = True
) -> List[Dict]:
    """
    Search for people mentioned in text by name.
    
    Args:
        text: The text to search for names
        people_index: The index returned by build_people_index()
        fuzzy: If True, use case-insensitive partial matching
        
    Returns:
        List of matching people dictionaries
    """
    if not people_index or "by_name" not in people_index:
        return []
    
    matches: List[Dict] = []
    seen_names = set()
    
    text_upper = text.upper()
    by_name = people_index["by_name"]
    
    for name, people_list in by_name.items():
        name_upper = name.upper()
        
        if fuzzy:
            # Case-insensitive word boundary matching
            pattern = r'\b' + re.escape(name_upper) + r'\b'
            if re.search(pattern, text_upper):
                for person in people_list:
                    if person["name"] not in seen_names:
                        matches.append(person)
                        seen_names.add(person["name"])
        else:
            # Exact matching
            if name_upper in text_upper:
                for person in people_list:
                    if person["name"] not in seen_names:
                        matches.append(person)
                        seen_names.add(person["name"])
    
    return matches


def search_people_by_title(
    text: str,
    people_index: Dict[str, List[Dict]],
    fuzzy: bool = True
) -> List[Dict]:
    """
    Search for people mentioned in text by title.
    
    Args:
        text: The text to search for titles
        people_index: The index returned by build_people_index()
        fuzzy: If True, use case-insensitive partial matching
        
    Returns:
        List of matching people dictionaries
    """
    if not people_index or "by_title" not in people_index:
        return []
    
    matches: List[Dict] = []
    seen_names = set()
    
    text_upper = text.upper()
    by_title = people_index["by_title"]
    
    for title, people_list in by_title.items():
        title_upper = title.upper()
        
        if fuzzy:
            # Case-insensitive word boundary matching for key parts of title
            # Extract key words (remove common words like "the", "and", etc.)
            title_words = [w for w in title_upper.split() if len(w) > 2]
            if title_words:
                # Check if any significant word from title appears in text
                for word in title_words:
                    pattern = r'\b' + re.escape(word) + r'\b'
                    if re.search(pattern, text_upper):
                        for person in people_list:
                            if person["name"] not in seen_names:
                                matches.append(person)
                                seen_names.add(person["name"])
                        break
        else:
            # Exact title matching
            if title_upper in text_upper:
                for person in people_list:
                    if person["name"] not in seen_names:
                        matches.append(person)
                        seen_names.add(person["name"])
    
    return matches


def extract_org_context_from_text(
    text: str,
    hierarchy: Optional[Dict] = None,
    people_index: Optional[Dict[str, List[Dict]]] = None
) -> Dict:
    """
    Extract organizational context relevant to the text.
    
    Args:
        text: The text content to analyze
        hierarchy: Optional pre-loaded hierarchy (will load if not provided)
        people_index: Optional pre-built people index (will build if not provided)
        
    Returns:
        Dictionary with:
            - "people_mentioned": List of people found in text
            - "organization": Organization name from hierarchy
    """
    context = {
        "people_mentioned": [],
        "organization": None,
    }
    
    # Load hierarchy if not provided
    if hierarchy is None:
        hierarchy = load_org_hierarchy()
    
    if not hierarchy:
        return context
    
    # Get organization name
    context["organization"] = hierarchy.get("organization")
    
    # Build index if not provided
    if people_index is None:
        people_index = build_people_index(hierarchy)
    
    # Search for people by name and title
    people_by_name = search_people_by_name(text, people_index, fuzzy=True)
    people_by_title = search_people_by_title(text, people_index, fuzzy=True)
    
    # Combine and deduplicate
    all_people = {}
    for person in people_by_name + people_by_title:
        name = person["name"]
        if name not in all_people:
            all_people[name] = person
    
    context["people_mentioned"] = list(all_people.values())
    
    return context


def format_org_context(org_context: Dict) -> str:
    """
    Format organizational context into a readable string for prompt injection.
    
    Args:
        org_context: Dictionary returned by extract_org_context_from_text()
        
    Returns:
        Formatted string describing the organizational context, or empty string if none
    """
    if not org_context or not org_context.get("people_mentioned"):
        return ""
    
    lines = ["Organizational context - people mentioned in the text:"]
    
    for person in org_context["people_mentioned"]:
        name = person.get("name", "")
        title = person.get("title", "")
        employee_id = person.get("employee_id")
        
        line = f"- {name}"
        if title:
            line += f", {title}"
        if employee_id:
            line += f" (ID: {employee_id})"
        
        lines.append(line)
    
    return "\n".join(lines)


__all__ = [
    "load_org_hierarchy",
    "build_people_index",
    "search_people_by_name",
    "search_people_by_title",
    "extract_org_context_from_text",
    "format_org_context",
]

