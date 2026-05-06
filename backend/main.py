# backend/main.py
# The FastAPI application — the web server that Streamlit talks to.
# Every @app.get() and @app.post() is a URL endpoint the frontend can call.

import uuid
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.database import (
    init_db, save_project, load_project,
    list_projects, delete_project
)
from backend.models import Project, ProjectStages, StageStatus
from backend.pipeline.stage1_parse import parse_transcript, apply_correction
from backend.pipeline.stage2_clarify import (
    generate_questions, process_answer, answer_user_question
)
from backend.pipeline.stage3_sow import generate_sow, revise_sow
from backend.pipeline.stage4_sprint import (
    generate_tasks_and_sprints, move_task_to_sprint, recalculate_sprint_points
)
from backend.pipeline.stage5_jira import push_epics, push_issues, push_sprints
from backend.services.jira_client import JiraClient


# Create the FastAPI app
app = FastAPI(
    title="Meeting Intelligence API",
    description="AI-powered meeting transcript to Jira sprint plan pipeline",
    version="1.0.0"
)

# Allow Streamlit (running on port 8501) to call this API (running on port 8000)
# Without this, browsers block cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event():
    """This runs once when the server starts. Creates the database table if needed."""
    init_db()
    print("Database initialized successfully.")


# ─────────────────────────────────────────────────────────────────
# PROJECT MANAGEMENT ENDPOINTS
# ─────────────────────────────────────────────────────────────────

@app.get("/projects")
def get_all_projects():
    """Return a list of all projects (just metadata, not full data)."""
    return list_projects()


@app.post("/projects")
def create_new_project(body: dict):
    """
    Create a new empty project.
    Expects: {"name": "My Project Name"}
    """
    if not body.get("name"):
        raise HTTPException(status_code=400, detail="Project name is required")

    project = Project(
        id=str(uuid.uuid4()),
        name=body["name"],
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
    )
    save_project(project)
    return project.model_dump()


@app.get("/projects/{project_id}")
def get_project(project_id: str):
    """Return full project data by ID."""
    project = load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return project.model_dump()


@app.delete("/projects/{project_id}")
def remove_project(project_id: str):
    """Permanently delete a project."""
    delete_project(project_id)
    return {"ok": True, "message": "Project deleted"}


# ─────────────────────────────────────────────────────────────────
# STAGE 1 ENDPOINTS
# ─────────────────────────────────────────────────────────────────

@app.post("/projects/{project_id}/stage1/parse")
def stage1_parse(project_id: str, body: dict):
    """
    Parse the transcript and extract structured information.
    Expects: {"transcript": "the full transcript text"}
    Returns the Stage1Output (modules, requirements, etc.)
    """
    project = load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    transcript = body.get("transcript", "").strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="Transcript text is required")

    # Store transcript and run the AI parsing
    project.transcript = transcript
    project.stage1_output = parse_transcript(transcript)
    save_project(project)

    return project.stage1_output.model_dump()


@app.post("/projects/{project_id}/stage1/correct")
def stage1_correct(project_id: str, body: dict):
    """
    Apply a plain-English correction to the Stage 1 extraction.
    Expects: {"correction": "The deadline is 8 weeks, not 6"}
    """
    project = load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.stage1_output:
        raise HTTPException(status_code=400, detail="Stage 1 has not been run yet")

    correction = body.get("correction", "").strip()
    if not correction:
        raise HTTPException(status_code=400, detail="Correction text is required")

    project.stage1_output = apply_correction(project.stage1_output, correction)
    save_project(project)

    return project.stage1_output.model_dump()


@app.post("/projects/{project_id}/stage1/approve")
def stage1_approve(project_id: str):
    """
    Approve Stage 1 — locks it as complete and unlocks Stage 2.
    No body needed.
    """
    project = load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.stage1_output:
        raise HTTPException(status_code=400, detail="Cannot approve — Stage 1 hasn't been run")

    project.stage1_approved = True
    project.stages.stage1 = StageStatus.COMPLETE
    project.stages.stage2 = StageStatus.ACTIVE
    save_project(project)

    return {"ok": True, "message": "Stage 1 approved. Stage 2 is now unlocked."}


# ─────────────────────────────────────────────────────────────────
# STAGE 2 ENDPOINTS
# ─────────────────────────────────────────────────────────────────

@app.post("/projects/{project_id}/stage2/generate_questions")
def stage2_generate_questions(project_id: str):
    """Generate clarification questions from Stage 1 gaps."""
    project = load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.stage1_approved:
        raise HTTPException(status_code=400, detail="Stage 1 must be approved first")

    project.clarification_questions = generate_questions(
        project.stage1_output,
        project.transcript
    )
    save_project(project)

    return [q.model_dump() for q in project.clarification_questions]


@app.post("/projects/{project_id}/stage2/answer/{question_id}")
def stage2_submit_answer(project_id: str, question_id: str, body: dict):
    """
    Submit an answer to a clarification question.
    Expects: {"answer": "the user's answer text"}
    """
    project = load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    answer = body.get("answer", "").strip()
    if not answer:
        raise HTTPException(status_code=400, detail="Answer text is required")

    # Build context from other answered questions
    qa_context = "\n".join([
        f"Q: {q.question}\nA: {q.answer}"
        for q in project.clarification_questions
        if q.answer
    ])

    # Find and update the question
    found = False
    for i, q in enumerate(project.clarification_questions):
        if q.id == question_id:
            project.clarification_questions[i] = process_answer(q, answer, qa_context)
            found = True
            break

    if not found:
        raise HTTPException(status_code=404, detail="Question not found")

    save_project(project)
    return [q.model_dump() for q in project.clarification_questions]


@app.post("/projects/{project_id}/stage2/skip/{question_id}")
def stage2_skip_question(project_id: str, question_id: str, body: dict):
    """
    Skip a question with a reason.
    Expects: {"reason": "Why we're skipping this"}
    """
    project = load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    for q in project.clarification_questions:
        if q.id == question_id:
            q.skipped = True
            q.resolved = True
            q.skip_reason = body.get("reason", "Skipped by user")
            break

    save_project(project)
    return {"ok": True}


@app.post("/projects/{project_id}/stage2/ask")
def stage2_user_asks_question(project_id: str, body: dict):
    """
    Let the user ask their own question about the project.
    Expects: {"question": "Can we fit the reporting module into Sprint 2?"}
    Returns: {"answer": "..."}
    """
    project = load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    user_question = body.get("question", "").strip()
    if not user_question:
        raise HTTPException(status_code=400, detail="Question is required")

    context = {
        "project_name": project.name,
        "stage1": project.stage1_output.model_dump() if project.stage1_output else {},
        "clarification_qa": [
            {"q": q.question, "a": q.answer}
            for q in project.clarification_questions
            if q.answer
        ]
    }

    answer = answer_user_question(user_question, context)
    return {"answer": answer}


@app.post("/projects/{project_id}/stage2/approve")
def stage2_approve(project_id: str):
    """Approve Stage 2 and unlock Stage 3."""
    project = load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project.stage2_approved = True
    project.stages.stage2 = StageStatus.COMPLETE
    project.stages.stage3 = StageStatus.ACTIVE
    save_project(project)

    return {"ok": True, "message": "Stage 2 approved. Stage 3 is now unlocked."}


# ─────────────────────────────────────────────────────────────────
# STAGE 3 ENDPOINTS
# ─────────────────────────────────────────────────────────────────

@app.post("/projects/{project_id}/stage3/generate")
def stage3_generate_sow(project_id: str):
    """Generate the initial Scope of Work document."""
    project = load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.stage2_approved:
        raise HTTPException(status_code=400, detail="Stage 2 must be approved first")

    sow = generate_sow(project.stage1_output, project.clarification_questions)
    project.scope_of_work = sow
    project.sow_version = 1
    save_project(project)

    return {"sow": sow, "version": 1}


@app.post("/projects/{project_id}/stage3/revise")
def stage3_revise_sow(project_id: str, body: dict):
    """
    Revise the SoW based on user feedback.
    Expects: {"feedback": "Plain English feedback about what to change"}
    Returns: {"sow": "revised text", "changelog": "what changed", "version": 2}
    """
    project = load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.scope_of_work:
        raise HTTPException(status_code=400, detail="SoW hasn't been generated yet")

    feedback = body.get("feedback", "").strip()
    if not feedback:
        raise HTTPException(status_code=400, detail="Feedback text is required")

    new_sow, changelog = revise_sow(
        project.scope_of_work,
        feedback,
        project.stage1_output
    )
    project.scope_of_work = new_sow
    project.sow_version += 1
    save_project(project)

    return {
        "sow": new_sow,
        "changelog": changelog,
        "version": project.sow_version
    }


@app.post("/projects/{project_id}/stage3/approve")
def stage3_approve(project_id: str):
    """
    Approve the SoW and unlock Stage 4.
    Requires at least one revision (version >= 2).
    """
    project = load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.sow_version < 2:
        raise HTTPException(
            status_code=400,
            detail="You must provide at least one round of feedback before approving the SoW"
        )

    project.stage3_approved = True
    project.stages.stage3 = StageStatus.COMPLETE
    project.stages.stage4 = StageStatus.ACTIVE
    save_project(project)

    return {"ok": True, "message": "SoW approved. Stage 4 is now unlocked."}


# ─────────────────────────────────────────────────────────────────
# STAGE 4 ENDPOINTS
# ─────────────────────────────────────────────────────────────────

@app.post("/projects/{project_id}/stage4/generate")
def stage4_generate_sprint_plan(project_id: str):
    """Generate tasks and sprint plan from the approved SoW."""
    project = load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.stage3_approved:
        raise HTTPException(status_code=400, detail="Stage 3 must be approved first")

    tasks, sprints = generate_tasks_and_sprints(
        project.scope_of_work,
        project.stage1_output
    )
    project.tasks = tasks
    project.sprints = sprints
    save_project(project)

    return {
        "tasks": [t.model_dump() for t in tasks],
        "sprints": [s.model_dump() for s in sprints]
    }


@app.post("/projects/{project_id}/stage4/move_task")
def stage4_move_task(project_id: str, body: dict):
    """
    Move a task to a different sprint.
    Expects: {"task_id": "T001", "sprint": "Sprint 2 — Integration"}
    """
    project = load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    task_id = body.get("task_id")
    new_sprint = body.get("sprint")
    if not task_id or not new_sprint:
        raise HTTPException(status_code=400, detail="task_id and sprint are required")

    project.tasks = move_task_to_sprint(project.tasks, task_id, new_sprint)
    project.sprints = recalculate_sprint_points(project.tasks, project.sprints)
    save_project(project)

    return {
        "tasks": [t.model_dump() for t in project.tasks],
        "sprints": [s.model_dump() for s in project.sprints]
    }


@app.post("/projects/{project_id}/stage4/approve")
def stage4_approve(project_id: str):
    """Approve the sprint plan and unlock Stage 5."""
    project = load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project.stage4_approved = True
    project.stages.stage4 = StageStatus.COMPLETE
    project.stages.stage5 = StageStatus.ACTIVE
    save_project(project)

    return {"ok": True, "message": "Sprint plan approved. Stage 5 (Jira sync) is now unlocked."}


# ─────────────────────────────────────────────────────────────────
# STAGE 5 ENDPOINTS
# ─────────────────────────────────────────────────────────────────

@app.post("/projects/{project_id}/stage5/test_connection")
def stage5_test_jira(project_id: str, body: dict):
    import os
    from dotenv import load_dotenv
    load_dotenv()

    domain    = os.getenv("JIRA_DOMAIN")      or body.get("domain", "")
    email     = os.getenv("JIRA_EMAIL")       or body.get("email", "")
    api_token = os.getenv("JIRA_API_TOKEN")   or body.get("api_token", "")
    proj_key  = os.getenv("JIRA_PROJECT_KEY") or body.get("project_key", "")

    domain = domain.replace("https://", "").replace("http://", "").strip("/")

    if not all([domain, email, api_token, proj_key]):
        raise HTTPException(status_code=400, detail="Missing Jira credentials — check your .env file")

    try:
        client = JiraClient(domain, email, api_token, proj_key)
        result = client.test_connection()

        project = load_project(project_id)
        if project:
            project.jira_config = {
                "domain": domain,
                "email": email,
                "api_token": api_token,
                "project_key": proj_key,
            }
            save_project(project)

        return result

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/projects/{project_id}/stage5/push_epics")
def stage5_push_epics(project_id: str):
    """Create Jira Epics for all modules. Must run before push_issues."""
    project = load_project(project_id)
    if not project or not project.jira_config:
        raise HTTPException(status_code=400, detail="Jira not configured or project not found")
    if not project.stage4_approved:
        raise HTTPException(status_code=400, detail="Stage 4 must be approved first")

    try:
        results, epic_map = push_epics(project)

        if not project.jira_results:
            project.jira_results = {}
        project.jira_results["epic_map"] = epic_map
        save_project(project)

        return results

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/projects/{project_id}/stage5/push_issues")
def stage5_push_issues(project_id: str):
    """Create Jira issues for all tasks. Must run after push_epics."""
    project = load_project(project_id)
    if not project or not project.jira_config:
        raise HTTPException(status_code=400, detail="Jira not configured")
    if not project.jira_results or "epic_map" not in project.jira_results:
        raise HTTPException(status_code=400, detail="Epics must be created first")

    try:
        results, issue_map = push_issues(project, project.jira_results["epic_map"])

        project.jira_results["issue_map"] = issue_map
        save_project(project)

        return results

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/projects/{project_id}/stage5/push_sprints")
def stage5_push_sprints(project_id: str):
    """Create sprints and assign issues. Must run last."""
    project = load_project(project_id)
    if not project or not project.jira_config:
        raise HTTPException(status_code=400, detail="Jira not configured")
    if not project.jira_results or "issue_map" not in project.jira_results:
        raise HTTPException(status_code=400, detail="Issues must be created first")

    try:
        results = push_sprints(project, project.jira_results["issue_map"])

        project.stage5_complete = True
        project.stages.stage5 = StageStatus.COMPLETE
        save_project(project)

        return results

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Health check — useful to test if the server is running
@app.get("/health")
def health_check():
    return {"status": "ok", "message": "Meeting Intelligence API is running"}