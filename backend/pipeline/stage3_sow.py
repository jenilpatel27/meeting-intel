# backend/pipeline/stage3_sow.py
# Stage 3: Generate and revise the Scope of Work document.
# The AI writes a professional SoW from Stage 1 + Stage 2 data.
# The user gives feedback, the AI revises, and we track a changelog.

from backend.services.llm import run_prompt
from backend.models import Stage1Output, ClarificationQuestion


SOW_SYSTEM = """You are a senior technical project manager writing professional 
Scope of Work documents for software development projects.

Writing style:
- Clear, professional, and specific
- Use actual names, dates, and numbers from the input — never say "TBD" unless it's genuinely unknown
- Use markdown formatting (## headers, bullet points, tables)
- Be explicit about what is OUT of scope — this prevents scope creep

Format each module section with:
- Feature description
- Acceptance criteria (numbered list)"""


def generate_sow(
    stage1: Stage1Output,
    questions: list[ClarificationQuestion]
) -> str:
    """
    Generate the full Scope of Work document.
    
    Combines Stage 1 extracted data with all the clarification Q&A
    to write a comprehensive SoW in markdown format.
    """

    # Build Q&A context string
    qa_lines = []
    for q in questions:
        if q.answer and not q.skipped:
            qa_lines.append(f"Q: {q.question}")
            qa_lines.append(f"A: {q.answer}")
            if q.follow_ups:
                for fu in q.follow_ups:
                    if fu.get("answer"):
                        qa_lines.append(f"  Follow-up Q: {fu['question']}")
                        qa_lines.append(f"  Follow-up A: {fu['answer']}")
            qa_lines.append("")
    qa_context = "\n".join(qa_lines) if qa_lines else "No clarifications were provided."

    modules_text = "\n".join([
        f"- **{m.name}** (Priority: {m.priority}"
        + (f", Deadline: {m.deadline}" if m.deadline else "")
        + f"): {m.description}"
        for m in stage1.modules
    ])

    integrations_text = "\n".join([
        f"- {i.name}: {i.description}"
        for i in stage1.integrations
    ])

    constraints_text = "\n".join([
        f"- {c.description}"
        for c in stage1.constraints
    ])

    unknowns_text = "\n".join([
        f"- {u.description}"
        for u in stage1.unknowns
    ])

    result = run_prompt(
        system=SOW_SYSTEM,
        user=f"""Write a complete Scope of Work document for this project.

PROJECT INFORMATION:
- Project Name: {stage1.project_name}
- Client: {stage1.client_name}
- Vendor: {stage1.vendor_name}

MODULES:
{modules_text}

INTEGRATIONS:
{integrations_text}

CONSTRAINTS:
{constraints_text}

CLARIFICATION Q&A:
{qa_context}

OPEN ITEMS (still unresolved):
{unknowns_text if unknowns_text else "None"}

Write the SoW with ALL of these sections (use ## for section headers):
## Executive Summary
## In-Scope Items
## Out-of-Scope Items
## Modules and Deliverables
## Integrations
## Constraints and Assumptions
## Open Items
## Timeline Overview"""
    )

    return result


def revise_sow(
    current_sow: str,
    feedback: str,
    stage1: Stage1Output
) -> tuple[str, str]:
    """
    Revise the SoW based on user feedback.
    
    Returns a tuple: (revised_sow_text, changelog_text)
    The changelog lists every change made so the user knows what was updated.
    """

    result = run_prompt(
        system=SOW_SYSTEM + """

IMPORTANT OUTPUT FORMAT:
First write the complete revised Scope of Work.
Then write exactly this separator on its own line: ---CHANGELOG---
Then write a numbered list of every change you made.""",

        user=f"""Here is the current Scope of Work:

{current_sow}

The user has provided this feedback:
{feedback}

Revise the SoW to incorporate ALL feedback points.
Be specific in the changelog — list each individual change."""
    )

    # Split on the separator we asked the AI to include
    if "---CHANGELOG---" in result:
        parts = result.split("---CHANGELOG---", 1)
        revised_sow = parts[0].strip()
        changelog = parts[1].strip()
    else:
        # Fallback if the AI didn't include the separator
        revised_sow = result
        changelog = "Revisions applied based on user feedback."

    return revised_sow, changelog