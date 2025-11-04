"""Context modules for providing additional context to agents."""

from .abbreviations import (
    load_abbreviations_dict,
    extract_relevant_abbreviations,
    format_abbreviations_context,
)
from .org_hierarchy import (
    load_org_hierarchy,
    build_people_index,
    search_people_by_name,
    search_people_by_title,
    extract_org_context_from_text,
    format_org_context,
)
from .personal_context import (
    load_personal_context,
    extract_professional_context,
    extract_relevant_context_for_text,
    format_personal_context,
)

__all__ = [
    # Abbreviations
    "load_abbreviations_dict",
    "extract_relevant_abbreviations",
    "format_abbreviations_context",
    # Org hierarchy
    "load_org_hierarchy",
    "build_people_index",
    "search_people_by_name",
    "search_people_by_title",
    "extract_org_context_from_text",
    "format_org_context",
    # Personal context
    "load_personal_context",
    "extract_professional_context",
    "extract_relevant_context_for_text",
    "format_personal_context",
]
