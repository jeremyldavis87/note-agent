VISION_EXTRACTION_PROMPT = (
    "You are a vision OCR expert. Read the image and extract the text content along with visual metadata. "
    "Preserve line breaks, bullets (-, •), numbered lists, and checkboxes (☐/☑). "
    "If you see titles with ##Title## syntax, include them. "
    "\n\n"
    "Return a JSON object with the following fields:\n"
    "- text: The extracted text content (string)\n"
    "- note_color: The color of the note (string, one of: orange, green, blue, yellow, pink, purple, red, or null if uncertain)\n"
    "- qr_code_present: Whether a QR code is visible in the note (boolean, true/false)\n"
    "- qr_code_position: Position of QR code relative to the note (string, one of: top_left, top_right, bottom_left, bottom_right, or null if no QR code)\n"
    "\n"
    "If you cannot return JSON, return plain text as a fallback. The text field should contain all the extracted text content."
)

TEXT_ENRICH_PROMPT = (
    "From the provided note text, generate: action items (imperative), normalized tags, and fix minor OCR artifacts. "
    "Extract the note title if present. Titles may be explicitly marked with ##Title## syntax, or may be the first line if it appears to be a title (not a bullet point, checkbox, or numbered item). Return null if no clear title exists. "
    "Return JSON with fields title, action_items, and tags."
)


def build_vision_prompt(
    abbreviations_context: str = "",
    org_context: str = ""
) -> str:
    """
    Build the vision extraction prompt with optional context snippets.
    
    Args:
        abbreviations_context: Formatted string containing relevant abbreviations.
                               Empty string if no abbreviations found.
        org_context: Formatted string containing organizational context (e.g., common terms).
                     Empty string if no context found.
    
    Returns:
        Complete vision extraction prompt with context if provided.
    """
    base_prompt = VISION_EXTRACTION_PROMPT
    
    context_parts = []
    
    if abbreviations_context:
        context_parts.append(abbreviations_context)
    
    if org_context:
        context_parts.append(org_context)
    
    if context_parts:
        context_section = "\n\n".join(context_parts)
        return f"{base_prompt}\n\nAdditional context to help with OCR recognition:\n{context_section}"
    
    return base_prompt


def build_text_enrich_prompt(
    abbreviations_context: str = "",
    org_context: str = "",
    personal_context: str = ""
) -> str:
    """
    Build the text enrichment prompt with optional context snippets.
    
    Args:
        abbreviations_context: Formatted string containing relevant abbreviations.
                               Empty string if no abbreviations found.
        org_context: Formatted string containing organizational context (people mentioned, etc.).
                    Empty string if no context found.
        personal_context: Formatted string containing personal/professional context.
                          Empty string if no context found.
    
    Returns:
        Complete text enrichment prompt with context if provided.
    """
    base_prompt = (
        "From the provided note text, extract ALL action items, normalized tags, and fix minor OCR artifacts. "
        "Extract the note title if present. Titles may be explicitly marked with ##Title## syntax, or may be the first line if it appears to be a title (not a bullet point, checkbox, or numbered item). Return null if no clear title exists. "
        "\n\n"
        "ACTION ITEMS: Extract ALL actionable items from the text. This includes:\n"
        "- Bullet points (•, -, *) that describe tasks or actions\n"
        "- Checkbox items (☐) - these are always action items\n"
        "- Statements that imply actions (e.g., 'Follow up on X', 'Discuss Y', 'Review Z')\n"
        "- Any mention of things to do, schedule, review, discuss, or address\n"
        "- Convert all action items to imperative form (e.g., 'Schedule meeting' not 'Need to schedule meeting')\n"
        "- Be comprehensive - extract every actionable item, not just the most obvious ones\n"
        "\n"
        "Return JSON with fields title, action_items (array of strings), and tags (array of strings)."
    )
    
    context_parts = []
    
    if abbreviations_context:
        context_parts.append(abbreviations_context)
    
    if org_context:
        context_parts.append(org_context)
    
    if personal_context:
        context_parts.append(personal_context)
    
    if context_parts:
        context_section = "\n\n".join(context_parts)
        return f"{base_prompt}\n\n{context_section}"
    
    return base_prompt
