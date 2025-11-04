"""Personal context dictionary management for agent context."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..logging_setup import setup_logging
import logging
from .utils import _load_context_file

logger = logging.getLogger(__name__)


def _validate_personal_context(data: Any) -> bool:
    """
    Validate that the personal context data has the correct structure.
    
    Args:
        data: The loaded JSON data
        
    Returns:
        True if valid, False otherwise
    """
    if not isinstance(data, dict):
        return False
    return True


def load_personal_context() -> Dict:
    """
    Load personal context from agent-context/personal-context.json.
    
    Returns:
        Dictionary containing personal context structure.
        Returns empty dict if file is missing or malformed.
    """
    return _load_context_file(
        "personal-context.json",
        validate_func=_validate_personal_context,
        description="personal context"
    )


def extract_professional_context(personal_context: Optional[Dict] = None) -> Dict:
    """
    Extract professional/organizational context from personal context.
    
    Args:
        personal_context: Optional pre-loaded personal context (will load if not provided)
        
    Returns:
        Dictionary with:
            - "company": Company name
            - "division": Division name
            - "title": Job title
            - "team_pillars": List of team pillar names
            - "organization_pillars": List of organization pillar names
            - "direct_reports": List of direct report names
            - "key_responsibilities": List of key responsibilities
    """
    context = {
        "company": None,
        "division": None,
        "title": None,
        "team_pillars": [],
        "organization_pillars": [],
        "direct_reports": [],
        "key_responsibilities": [],
    }
    
    # Load context if not provided
    if personal_context is None:
        personal_context = load_personal_context()
    
    if not personal_context:
        return context
    
    # Extract professional information
    prof_info = personal_context.get("professional_information", {})
    if not prof_info:
        return context
    
    # Current employment
    current_employment = prof_info.get("current_employment", {})
    context["company"] = current_employment.get("company")
    context["division"] = current_employment.get("division")
    context["title"] = current_employment.get("title")
    
    # Organizational structure
    org_structure = prof_info.get("organizational_structure", {})
    
    # Team pillars
    team_pillars = org_structure.get("team_pillars", [])
    context["team_pillars"] = [pillar.get("name", "") for pillar in team_pillars if isinstance(pillar, dict)]
    
    # Organization pillars
    org_pillars = org_structure.get("organization_pillars", [])
    context["organization_pillars"] = [pillar.get("name", "") for pillar in org_pillars if isinstance(pillar, dict)]
    
    # Direct reports
    direct_reports = prof_info.get("direct_reports", {})
    team_members = direct_reports.get("team_members", [])
    tecdp_associates = direct_reports.get("tecdp_associates", [])
    context["direct_reports"] = list(team_members) + list(tecdp_associates)
    
    # Key responsibilities
    key_responsibilities = prof_info.get("key_responsibilities", [])
    context["key_responsibilities"] = list(key_responsibilities)
    
    return context


def extract_relevant_context_for_text(
    text: str,
    personal_context: Optional[Dict] = None
) -> Dict:
    """
    Extract relevant context from personal context based on text content.
    
    Args:
        text: The text content to analyze
        personal_context: Optional pre-loaded personal context (will load if not provided)
        
    Returns:
        Dictionary with relevant context for the text
    """
    context = {
        "professional_context": {},
        "teams_mentioned": [],
        "projects_mentioned": [],
        "responsibilities_mentioned": [],
    }
    
    # Load context if not provided
    if personal_context is None:
        personal_context = load_personal_context()
    
    if not personal_context:
        return context
    
    # Get professional context
    prof_context = extract_professional_context(personal_context)
    context["professional_context"] = prof_context
    
    # Check if text mentions teams, projects, or responsibilities
    text_upper = text.upper()
    
    # Check for team pillar mentions
    for pillar in prof_context.get("team_pillars", []):
        if pillar.upper() in text_upper:
            context["teams_mentioned"].append(pillar)
    
    # Check for organization pillar mentions
    for pillar in prof_context.get("organization_pillars", []):
        if pillar.upper() in text_upper:
            context["teams_mentioned"].append(pillar)
    
    # Check for direct report mentions
    for name in prof_context.get("direct_reports", []):
        if name.upper() in text_upper:
            context["teams_mentioned"].append(f"Team member: {name}")
    
    # Check for project mentions
    active_projects = personal_context.get("active_projects", {})
    for project_key, project_info in active_projects.items():
        if isinstance(project_info, dict):
            project_name = project_info.get("name") or project_key
            if project_name.upper() in text_upper:
                context["projects_mentioned"].append(project_name)
            # Also check description
            description = project_info.get("description", "")
            if description and description.upper() in text_upper:
                context["projects_mentioned"].append(project_name)
    
    # Check for responsibility mentions
    for responsibility in prof_context.get("key_responsibilities", []):
        # Check if key words from responsibility appear in text
        resp_words = [w for w in responsibility.upper().split() if len(w) > 4]
        if any(word in text_upper for word in resp_words):
            context["responsibilities_mentioned"].append(responsibility)
    
    return context


def format_personal_context(personal_context: Dict) -> str:
    """
    Format personal/professional context into a readable string for prompt injection.
    
    Args:
        personal_context: Dictionary returned by extract_relevant_context_for_text()
        
    Returns:
        Formatted string describing the personal context, or empty string if none
    """
    if not personal_context:
        return ""
    
    lines = []
    
    # Professional context
    prof_context = personal_context.get("professional_context", {})
    if prof_context:
        lines.append("Professional context:")
        
        if prof_context.get("company"):
            lines.append(f"- Company: {prof_context['company']}")
        if prof_context.get("division"):
            lines.append(f"- Division: {prof_context['division']}")
        if prof_context.get("title"):
            lines.append(f"- Title: {prof_context['title']}")
    
    # Teams mentioned
    teams = personal_context.get("teams_mentioned", [])
    if teams:
        lines.append("\nTeams/Organizational units mentioned:")
        for team in teams:
            lines.append(f"- {team}")
    
    # Projects mentioned
    projects = personal_context.get("projects_mentioned", [])
    if projects:
        lines.append("\nProjects mentioned:")
        for project in projects:
            lines.append(f"- {project}")
    
    # Responsibilities mentioned
    responsibilities = personal_context.get("responsibilities_mentioned", [])
    if responsibilities:
        lines.append("\nRelevant responsibilities:")
        for resp in responsibilities:
            lines.append(f"- {resp}")
    
    if not lines:
        return ""
    
    return "\n".join(lines)


__all__ = [
    "load_personal_context",
    "extract_professional_context",
    "extract_relevant_context_for_text",
    "format_personal_context",
]

