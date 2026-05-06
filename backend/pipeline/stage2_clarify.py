# backend/pipeline/stage2_clarify.py
# Stage 2: Generate targeted clarification questions from the gaps found in Stage 1.
# The AI asks smart questions — no generic filler allowed.

import uuid
from backend.services.llm import run_json_prompt, run_prompt
from backend.models import Stage1Output, ClarificationQuestion


def generate_questions(
    stage1: Stage1Output,
    transcript: str
) -> list[ClarificationQuestion]:
    """
    Look at what was extracted in Stage 1 and generate targeted questions
    for anything unclear, missing, or unresolved.
    
    Returns a list of ClarificationQuestion objects.
    """

    # Build a summary of the gaps we need to ask about
    unknowns_text = "\n".join([f"- {u.description}" for u in stage1.unknowns])
    assumptions_text = "\n".join([f"- {a.description} (confidence: {a.confidence})" for a in stage1.assumptions])
    low_confidence = [i for i in stage1.integrations if i.confidence < 0.7]
    low_conf_text = "\n".join([f"- {i.name}: {i.description}" for i in low_confidence])

    result = run_json_prompt(
        system="""You are an expert project manager preparing for a project kickoff.
Your job is to generate targeted clarification questions based on gaps in a project extraction.

Rules for questions:
- Minimum 5 questions, no maximum
- Every question MUST cite something specific from the transcript as the reason
- No generic questions like "Can you tell me more about the project?"
- Focus on: unresolved API details, budget, compliance specifics, out-of-scope items,
  timeline ambiguities, integration authentication methods
- Questions should help unlock information needed to write a good Scope of Work""",

        user=f"""Here is the transcript excerpt (first 3000 chars):
{transcript[:3000]}

Extracted unknowns:
{unknowns_text if unknowns_text else "None found"}

Low-confidence assumptions:
{assumptions_text if assumptions_text else "None found"}

Integrations needing clarification:
{low_conf_text if low_conf_text else "None found"}

Generate clarification questions as a JSON array:
[
  {{
    "question": "The specific question to ask",
    "reason": "Why this is being asked — cite something specific from the transcript or extraction"
  }}
]"""
    )

    # Convert each dict into a ClarificationQuestion object
    questions = []
    for q in result:
        questions.append(ClarificationQuestion(
            id=str(uuid.uuid4()),   # Random unique ID
            question=q["question"],
            reason=q["reason"],
        ))

    return questions


def process_answer(
    question: ClarificationQuestion,
    answer: str,
    all_qa_context: str
) -> ClarificationQuestion:
    """
    Process a user's answer to a clarification question.
    The AI decides: is this answer complete, or do we need a follow-up question?
    
    Returns the updated question with the answer filled in.
    """

    result = run_json_prompt(
        system="""You are a project manager reviewing a clarification answer.
Decide if the answer fully resolves the question or if a follow-up is needed.
Be practical — don't generate follow-ups for every answer, only when genuinely needed.
Return ONLY this JSON: {"resolved": true or false, "follow_up": "follow-up question or null"}""",

        user=f"""Original question: {question.question}

User's answer: {answer}

Context from other questions already answered:
{all_qa_context[:800]}

Is this answer complete enough to move forward?
If yes: resolved = true, follow_up = null
If a critical detail is still missing: resolved = false, follow_up = "specific follow-up question" """
    )

    question.answer = answer
    question.resolved = result.get("resolved", True)

    follow_up = result.get("follow_up")
    if follow_up and follow_up != "null":
        question.follow_ups.append({"question": follow_up, "answer": None})

    return question


def answer_user_question(user_question: str, context: dict) -> str:
    """
    Let the user ask their own questions about the project.
    Example: "Can we fit the reporting module into Sprint 2?"
    
    The AI answers using all available context.
    """
    return run_prompt(
        system="You are a senior project manager with full context of this project. Answer the user's question directly and helpfully based on the available information.",
        user=f"""Project context:
{str(context)[:2000]}

User's question: {user_question}

Answer directly and concisely."""
    )