VISION_EXTRACTION_PROMPT = (
    "You are a vision OCR expert. Read the image of notes and extract: "
    "1) count of notes and a 3x3 grid position per note when applicable (row_X_col_Y), "
    "2) title or header if present (recognize '##Title##' syntax), "
    "3) raw text preserving line breaks, bullets (-, •), numbered lists, and checkboxes (☐/☑), "
    "4) normalized formatted_text with bullets as '•' and headers preserved, "
    "5) tags (@tag and ::key:value) if visible, and an estimated confidence (0-1). "
    "Return strictly as JSON per the provided schema for each note; do not include commentary."
)

TEXT_ENRICH_PROMPT = (
    "From the provided note text, generate: action items (imperative), normalized tags, and fix minor OCR artifacts. "
    "Return JSON with fields action_items and tags only."
)
