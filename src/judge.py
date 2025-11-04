"""LLM-as-a-judge for comparing image input against JSON output."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import cv2

from .config import settings
from .llm.factory import get_clients
from .llm.base import VisionInput
from .schema import Document
from .logging_setup import setup_logging
import logging

logger = logging.getLogger(__name__)


JUDGE_PROMPT = """You are an expert judge evaluating the quality of note extraction from an image.

Your task is to compare the original image of notes against the extracted JSON output and provide feedback for improvements.

IMPORTANT CONTEXT: The extraction agents that processed this image were augmented with additional context including:
- Organizational abbreviations (e.g., HIH = Hyderabad Innovation Hub, EMG = Enterprise Model Governance, PIF = Procurement Intake Form)
- Organizational hierarchy information
- Personal/professional context

However, you (the judge) do NOT need this context - evaluate the output based on:
1. Accuracy of text extraction from the image
2. Correctness of structure recognition (titles, bullets, checkboxes)
3. Completeness of all visible notes
4. Quality of action item generation
5. Relevance and completeness of tags
6. Any missing information visible in the image

Please provide a structured JSON response with:
{
  "overall_score": 0.0-1.0,
  "issues_found": [
    {
      "severity": "critical" | "major" | "minor",
      "note_position": "row_X_col_Y" or "general",
      "issue_type": "missing_text" | "incorrect_text" | "missing_structure" | "missing_action_items" | "missing_tags" | "other",
      "description": "Detailed description of the issue",
      "suggestion": "Specific suggestion for improvement"
    }
  ],
  "strengths": ["List of things done well"],
  "recommendations": ["High-level recommendations for improvement"]
}

Focus on factual accuracy and completeness - do not penalize the agents for using context augmentation, but ensure the base extraction is correct.
"""


def judge_extraction(
    image_path: Path,
    document: Document,
    *,
    max_tokens: Optional[int] = None
) -> dict:
    """
    Judge the quality of extraction by comparing image against JSON output.
    
    Args:
        image_path: Path to the original image
        document: The extracted Document object
        max_tokens: Optional max tokens for judge response
        
    Returns:
        Dictionary with judge evaluation results
    """
    setup_logging()
    
    # Load image
    bgr = cv2.imread(str(image_path))
    if bgr is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")
    
    # Encode image for vision model
    _, jpeg = cv2.imencode(".jpg", bgr)
    
    # Convert document to JSON for comparison
    document_json = document.model_dump_json(indent=2)
    
    # Get clients
    vision_client, text_client = get_clients()
    
    # Use vision client to get image description from judge's perspective
    vision_judge_prompt = (
        "Review this image of notes carefully. Note the text content, structure, "
        "number of notes, titles, bullets, checkboxes, and any other visible elements. "
        "Describe what you see in detail, especially focusing on the text content and structure."
    )
    
    try:
        image_description = vision_client.generate(
            VisionInput(image_bytes=jpeg.tobytes(), instructions=vision_judge_prompt),
            max_tokens=max_tokens or settings.AGENT_VISION_MODEL_MAX_OUTPUT_TOKENS,
        )
    except Exception as e:
        logger.warning(f"Vision judge failed: {e}")
        image_description = "Unable to extract image description"
    
    # Build comparison prompt
    comparison_prompt = f"""{JUDGE_PROMPT}

IMAGE DESCRIPTION (from judge's perspective):
{image_description}

EXTRACTED JSON OUTPUT:
{document_json}

Please compare the image description above against the extracted JSON output and provide your evaluation.
"""
    
    try:
        judge_response = text_client.generate(
            comparison_prompt,
            max_tokens=max_tokens or settings.TEXT_AI_MODEL_MAX_OUTPUT_TOKENS,
        )
        
        # Parse judge response
        try:
            judge_result = json.loads(judge_response)
        except json.JSONDecodeError:
            # If response isn't valid JSON, wrap it
            logger.warning("Judge response not valid JSON, wrapping response")
            judge_result = {
                "overall_score": None,
                "issues_found": [],
                "strengths": [],
                "recommendations": [judge_response],
                "raw_response": judge_response,
            }
        
        return judge_result
        
    except Exception as e:
        logger.error(f"Judge evaluation failed: {e}")
        return {
            "overall_score": None,
            "issues_found": [],
            "strengths": [],
            "recommendations": ["Judge evaluation failed"],
            "error": str(e),
        }


def judge_extraction_to_file(
    image_path: Path,
    document: Document,
    output_path: Path,
    *,
    max_tokens: Optional[int] = None
) -> None:
    """
    Judge extraction and save results to a file.
    
    Args:
        image_path: Path to the original image
        document: The extracted Document object
        output_path: Path to save judge results JSON
        max_tokens: Optional max tokens for judge response
    """
    judge_result = judge_extraction(image_path, document, max_tokens=max_tokens)
    output_path.write_text(json.dumps(judge_result, indent=2))


def apply_judge_feedback(
    document: Document,
    judge_result: dict
) -> Document:
    """
    Apply judge feedback to improve the document (optional - for future enhancement).
    
    Currently, this function returns the document unchanged.
    Future enhancements could automatically fix issues based on judge feedback.
    
    Args:
        document: The original Document
        judge_result: The judge evaluation results
        
    Returns:
        Potentially improved Document (currently returns unchanged)
    """
    # TODO: Implement automatic fixes based on judge feedback
    # For now, just return the original document
    return document


__all__ = ["judge_extraction", "judge_extraction_to_file", "apply_judge_feedback"]

