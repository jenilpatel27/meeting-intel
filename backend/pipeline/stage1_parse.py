# backend/pipeline/stage1_parse.py
# Stage 1: Parse the meeting transcript and extract structured information.
# The AI reads the transcript and fills in a structured form.

from backend.services.llm import run_json_prompt
from backend.models import Stage1Output


# This is the "system prompt" — it tells the AI what role to play
# and the rules for confidence scoring.
PARSE_SYSTEM = """You are an expert business analyst specializing in software project scoping.
Your job is to extract structured information from client meeting transcripts.

Confidence score rules (be honest — do not inflate scores):
- 1.0 = Explicitly stated word-for-word in the transcript
- 0.8 = Very clearly implied, almost certain
- 0.6 = Reasonably inferred from context
- 0.4 = Assumed based on typical projects — not stated
- 0.2 = Guessing — very uncertain

Always be thorough with unknowns. Flag anything mentioned but unresolved.
If a person said "I'll follow up on X", X is an unknown."""

def clean_ai_output(result: dict) -> dict:
    """
    Clean AI output before passing to Pydantic.
    Fixes common issues like invalid priority values or null strings.
    """
    valid_priorities = {"High", "Medium", "Low"}

    # Fix module priorities
    for module in result.get("modules", []):
        if module.get("priority") not in valid_priorities:
            module["priority"] = "Medium"

    # Fix requirement fields
    for req in result.get("requirements", []):
        if not req.get("module"):
            req["module"] = "General"
        if req.get("type") not in {"Functional", "Non-Functional", "Integration"}:
            req["type"] = "Functional"
        if not isinstance(req.get("confidence"), (int, float)):
            req["confidence"] = 0.5

    # Fix integration confidence
    for item in result.get("integrations", []):
        if not isinstance(item.get("confidence"), (int, float)):
            item["confidence"] = 0.5

    # Fix constraint confidence
    for item in result.get("constraints", []):
        if not isinstance(item.get("confidence"), (int, float)):
            item["confidence"] = 0.5

    # Fix assumption confidence
    for item in result.get("assumptions", []):
        if not isinstance(item.get("confidence"), (int, float)):
            item["confidence"] = 0.5

    return result

def parse_transcript(transcript: str) -> Stage1Output:
    """
    Take a raw transcript string and return a fully structured Stage1Output.
    
    This calls the Gemini API with a carefully crafted prompt asking it
    to extract all requirements, modules, integrations, etc.
    """

    result = run_json_prompt(
        system=PARSE_SYSTEM,
        user=f"""Analyze this meeting transcript carefully and extract all structured information.

TRANSCRIPT:
{transcript}

Return EXACTLY this JSON structure (no extra fields, no missing fields):
{{
  "project_name": "name of the project being discussed",
  "client_name": "name of the client company or person",
  "vendor_name": "name of the vendor/development company",
  "modules": [
    {{
      "name": "module name",
      "description": "what this module does",
      "priority": "High or Medium or Low",
      "deadline": "deadline string or null if not mentioned"
    }}
  ],
  "requirements": [
    {{
      "description": "what is required",
      "module": "which module this belongs to — NEVER null, use General if unsure",
      "type": "Functional or Non-Functional or Integration — NEVER null, default to Functional",
      "confidence": 0.0
    }}
  ],
  "integrations": [
    {{
      "name": "third-party system name",
      "description": "how it integrates / what it does",
      "confidence": 0.0
    }}
  ],
  "constraints": [
    {{
      "description": "timeline, budget, compliance, or technical constraint",
      "confidence": 0.0
    }}
  ],
  "assumptions": [
    {{
      "description": "something inferred but not explicitly stated",
      "confidence": 0.0
    }}
  ],
  "unknowns": [
    {{
      "description": "something mentioned but unresolved or needing follow-up"
    }}
  ]
}}"""
    )

    # Convert the dict from the AI into our Pydantic Stage1Output model
    # Pydantic will validate all fields and raise an error if something is wrong
    return Stage1Output(**clean_ai_output(result))


def apply_correction(current_output: Stage1Output, correction: str) -> Stage1Output:
    """
    Apply a plain-English correction to the current extraction.
    
    Example correction: "The deadline for the Returns module is 8 weeks, not 6"
    The AI updates the JSON accordingly and returns the full corrected version.
    """

    current_json = current_output.model_dump_json(indent=2)

    result = run_json_prompt(
        system=PARSE_SYSTEM + "\n\nYou will receive an existing extraction and a correction. Apply the correction precisely and return the complete updated JSON.",
        user=f"""Here is the current extraction:
{current_json}

The user wants to make this correction:
{correction}

Apply ONLY what the user asked to change. Keep everything else the same.
Return the complete updated JSON in the exact same structure."""
    )

    return Stage1Output(**result)