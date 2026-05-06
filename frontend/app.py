# frontend/app.py
# The Streamlit web application — the browser UI.
# Every st.button(), st.text_area(), st.expander() creates HTML automatically.
# No HTML/CSS/JavaScript needed.

import streamlit as st
import requests
import json

# The FastAPI server address — must match where uvicorn is running
API_URL = "http://localhost:8000"

# ─────────────────────────────────────────────────────────────────
# PAGE CONFIGURATION — must be the very first Streamlit command
# ─────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Meeting Intelligence",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ─────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────

def api_call(method: str, path: str, **kwargs) -> dict | None:
    """
    Make an HTTP call to the FastAPI backend.
    
    Shows a friendly error message if the API is unreachable.
    Returns the JSON response as a Python dict, or None on error.
    
    method = "GET", "POST", or "DELETE"
    path   = the URL path, e.g. "/projects" or "/projects/abc123/stage1/parse"
    kwargs = extra arguments like json={"key": "value"} for POST bodies
    """
    try:
        response = requests.request(
            method,
            f"{API_URL}{path}",
            timeout=120,    # 2 minutes — AI calls can take a while
            **kwargs
        )
        response.raise_for_status()   # Raise exception for 4xx/5xx errors
        return response.json()

    except requests.exceptions.ConnectionError:
        st.error(
            "⚠️ Cannot connect to the API server. "
            "Make sure you ran: `uvicorn backend.main:app --reload --port 8000` "
            "in a separate terminal."
        )
        return None

    except requests.exceptions.Timeout:
        st.error("⏱️ Request timed out. The AI is taking too long — please try again.")
        return None

    except requests.exceptions.HTTPError as e:
        # Try to show the actual error message from FastAPI
        try:
            error_detail = e.response.json().get("detail", str(e))
        except:
            error_detail = str(e)
        st.error(f"API Error: {error_detail}")
        return None

    except Exception as e:
        st.error(f"Unexpected error: {str(e)}")
        return None


def confidence_indicator(score: float) -> str:
    """Convert a 0.0-1.0 confidence score to a colored emoji indicator."""
    if score >= 0.8:
        return "🟢"    # High confidence — AI is sure
    elif score >= 0.5:
        return "🟡"    # Medium confidence — inferred
    else:
        return "🔴"    # Low confidence — AI is guessing


def priority_indicator(priority: str) -> str:
    """Convert priority string to colored indicator."""
    return {"High": "🔴", "Medium": "🟡", "Low": "🟢"}.get(priority, "⚪")


# ─────────────────────────────────────────────────────────────────
# SIDEBAR — Project Switcher
# ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🧠 Meeting Intel")
    st.caption("AI-powered transcript → Jira pipeline")
    st.divider()

    # ── Create new project ──
    st.subheader("New Project")
    new_project_name = st.text_input(
        "Project name",
        placeholder="e.g. Returns Management System",
        key="new_project_name_input"
    )
    if st.button("➕ Create Project", use_container_width=True, type="primary"):
        if new_project_name.strip():
            result = api_call("POST", "/projects", json={"name": new_project_name.strip()})
            if result:
                st.session_state["active_project_id"] = result["id"]
                #st.session_state["new_project_name_input"] = "" --> Showing error for creating new project !! Need to look into this. 
                st.success(f"Created: {new_project_name}")
                st.rerun()
        else:
            st.warning("Please enter a project name")

    st.divider()

    # ── List existing projects ──
    st.subheader("Your Projects")
    projects = api_call("GET", "/projects") or []

    if not projects:
        st.caption("No projects yet. Create one above.")
    else:
        for p in projects:
            is_active = st.session_state.get("active_project_id") == p["id"]

            col_btn, col_del = st.columns([5, 1])
            with col_btn:
                # Highlight the active project
                btn_label = f"{'▶ ' if is_active else ''}{p['name']}"
                if st.button(
                    btn_label,
                    key=f"switch_{p['id']}",
                    use_container_width=True,
                    type="primary" if is_active else "secondary"
                ):
                    st.session_state["active_project_id"] = p["id"]
                    st.rerun()

            with col_del:
                if st.button("🗑️", key=f"delete_{p['id']}", help="Delete this project"):
                    api_call("DELETE", f"/projects/{p['id']}")
                    # If we just deleted the active project, clear it
                    if st.session_state.get("active_project_id") == p["id"]:
                        del st.session_state["active_project_id"]
                    st.rerun()

    st.divider()
    st.caption("💡 Tip: Each project keeps its own state. Switching projects won't lose your work.")


# ─────────────────────────────────────────────────────────────────
# MAIN AREA — Show landing page if no project selected
# ─────────────────────────────────────────────────────────────────
if "active_project_id" not in st.session_state:
    st.title("Welcome to Meeting Intelligence 🧠")
    st.markdown("""
    ### Turn meeting transcripts into Jira sprints — step by step

    **How it works:**

    1. 📄 **Upload a transcript** — paste or upload your client meeting notes
    2. 🔍 **AI extracts** — requirements, modules, constraints, integrations
    3. ❓ **Clarification loop** — AI asks targeted questions, you answer
    4. 📋 **Scope of Work** — AI drafts it, you review and give feedback
    5. 🏃 **Sprint plan** — AI organizes tasks, you adjust and approve
    6. 🚀 **Jira sync** — everything pushed to Jira with one click

    **Every step requires your explicit approval before moving forward.**

    ---
    👈 **Create a new project in the sidebar to get started.**
    """)
    st.stop()   # Don't render anything below if no project is selected


# ─────────────────────────────────────────────────────────────────
# LOAD THE ACTIVE PROJECT
# ─────────────────────────────────────────────────────────────────
project_id = st.session_state["active_project_id"]
project = api_call("GET", f"/projects/{project_id}")

if not project:
    st.error("Could not load project. The API may be down.")
    st.stop()


# ─────────────────────────────────────────────────────────────────
# STAGE PROGRESS BAR — Always visible at the top
# ─────────────────────────────────────────────────────────────────
st.title(f"📋 {project['name']}")

stages_info = [
    ("1 · Parse", "stage1"),
    ("2 · Clarify", "stage2"),
    ("3 · Scope", "stage3"),
    ("4 · Sprint", "stage4"),
    ("5 · Jira", "stage5"),
]

progress_cols = st.columns(5)
for col, (label, key) in zip(progress_cols, stages_info):
    status = project["stages"][key]
    with col:
        if status == "complete":
            st.success(f"✅ {label}")
        elif status == "active":
            st.info(f"🔵 {label}")
        else:
            st.markdown(
                f'<div style="padding:8px;border-radius:8px;'
                f'background:#f0f0f0;color:#888;text-align:center;'
                f'font-size:0.85em">🔒 {label}</div>',
                unsafe_allow_html=True
            )

st.divider()


# ─────────────────────────────────────────────────────────────────
# TABS — One tab per stage
# ─────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📄 1 · Parse Transcript",
    "❓ 2 · Clarification",
    "📋 3 · Scope of Work",
    "🏃 4 · Sprint Plan",
    "🚀 5 · Jira Sync",
])


# ════════════════════════════════════════════════════════════════
# TAB 1 — TRANSCRIPT PARSING
# ════════════════════════════════════════════════════════════════
with tab1:
    st.header("Stage 1 — Transcript Parsing & Requirement Extraction")

    if project["stages"]["stage1"] == "complete":
        st.success("✅ Stage 1 has been approved and locked.")

    st.markdown("Upload or paste the client meeting transcript. The AI will extract all requirements, modules, integrations, and more.")

    # ── Input: upload file OR paste text ──
    col_upload, col_paste = st.columns([1, 2])

    with col_upload:
        uploaded_file = st.file_uploader(
            "Upload .txt file",
            type=["txt"],
            help="Upload a plain text file of the transcript"
        )

    with col_paste:
        # Pre-fill with existing transcript if project already has one
        existing_transcript = project.get("transcript") or ""
        pasted_transcript = st.text_area(
            "Or paste the transcript here",
            value=existing_transcript,
            height=200,
            placeholder="Paste the full meeting transcript here...",
        )

    # Determine which source to use
    final_transcript = None
    if uploaded_file:
        final_transcript = uploaded_file.read().decode("utf-8")
        st.info(f"📎 Using uploaded file: {uploaded_file.name}")
    elif pasted_transcript.strip():
        final_transcript = pasted_transcript.strip()

    # ── Parse button ──
    parse_disabled = not final_transcript
    if st.button(
        "🔍 Parse Transcript",
        type="primary",
        disabled=parse_disabled,
        help="This calls the Gemini AI to analyze the transcript"
    ):
        with st.spinner("🤖 AI is analyzing the transcript... (this takes 15-30 seconds)"):
            result = api_call(
                "POST",
                f"/projects/{project_id}/stage1/parse",
                json={"transcript": final_transcript}
            )
            if result:
                st.success("✅ Parsing complete!")
                st.rerun()

    # ── Display extraction results ──
    output = project.get("stage1_output")

    if output:
        st.divider()
        st.subheader("📊 Extraction Results")
        st.caption("🟢 = High confidence (explicitly stated)   🟡 = Medium (inferred)   🔴 = Low (guessing)")

        # Project info
        col_info, col_modules = st.columns(2)

        with col_info:
            st.markdown("#### Project Information")
            st.markdown(f"""
| Field | Value |
|-------|-------|
| **Project** | {output.get('project_name', 'Unknown')} |
| **Client** | {output.get('client_name', 'Unknown')} |
| **Vendor** | {output.get('vendor_name', 'Unknown')} |
            """)

            st.markdown("#### 🔗 Integrations")
            integrations = output.get("integrations", [])
            if integrations:
                for i in integrations:
                    badge = confidence_indicator(i["confidence"])
                    st.markdown(f"{badge} **{i['name']}** — {i['description']}")
            else:
                st.caption("No integrations found")

            st.markdown("#### ⚠️ Constraints")
            constraints = output.get("constraints", [])
            if constraints:
                for c in constraints:
                    badge = confidence_indicator(c["confidence"])
                    st.markdown(f"{badge} {c['description']}")
            else:
                st.caption("No constraints found")

        with col_modules:
            st.markdown("#### 🧩 Modules")
            modules = output.get("modules", [])
            if modules:
                for m in modules:
                    p_icon = priority_indicator(m["priority"])
                    deadline_text = f" | 📅 {m['deadline']}" if m.get("deadline") else ""
                    with st.expander(f"{p_icon} **{m['name']}** ({m['priority']}{deadline_text})"):
                        st.write(m["description"])
            else:
                st.warning("No modules extracted. Try correcting the extraction below.")

            st.markdown("#### ❓ Unknowns (need clarification)")
            unknowns = output.get("unknowns", [])
            if unknowns:
                for u in unknowns:
                    st.warning(f"🔍 {u['description']}")
            else:
                st.success("No unknowns found")

        # Requirements (collapsed by default)
        with st.expander(f"📋 Requirements ({len(output.get('requirements', []))} found)"):
            requirements = output.get("requirements", [])
            if requirements:
                for r in requirements:
                    badge = confidence_indicator(r["confidence"])
                    st.markdown(
                        f"{badge} `{r['type']}` · **{r['module']}** · {r['description']}"
                    )
            else:
                st.caption("No requirements extracted")

        with st.expander(f"💭 Assumptions ({len(output.get('assumptions', []))} found)"):
            assumptions = output.get("assumptions", [])
            for a in assumptions:
                badge = confidence_indicator(a["confidence"])
                st.markdown(f"{badge} {a['description']}")

        # ── Corrections ──
        st.divider()
        st.subheader("✏️ Request a Correction")
        st.caption("Describe what to change in plain English. The AI will update the extraction.")

        correction_text = st.text_input(
            "Correction",
            placeholder="e.g. The deadline for the Returns module is 8 weeks. The client name is Acme Corp.",
            key="correction_input"
        )

        if st.button("Apply Correction", disabled=not correction_text.strip()):
            with st.spinner("Updating extraction..."):
                result = api_call(
                    "POST",
                    f"/projects/{project_id}/stage1/correct",
                    json={"correction": correction_text.strip()}
                )
                if result:
                    st.success("Correction applied!")
                    st.rerun()

        # ── Approval ──
        st.divider()
        if project["stages"]["stage1"] != "complete":
            st.subheader("✅ Approve Stage 1")
            st.markdown("Once you approve, Stage 2 (Clarification) will unlock. **This cannot be undone.**")

            if st.button(
                "✅ Approve Extraction & Unlock Stage 2",
                type="primary",
                use_container_width=True
            ):
                result = api_call("POST", f"/projects/{project_id}/stage1/approve")
                if result:
                    st.success("Stage 1 approved! Move to the Clarification tab.")
                    st.rerun()
        else:
            st.success("✅ Stage 1 approved and locked.")

    else:
        st.info("👆 Parse a transcript above to see the extraction results here.")


# ════════════════════════════════════════════════════════════════
# TAB 2 — CLARIFICATION LOOP
# ════════════════════════════════════════════════════════════════
with tab2:
    st.header("Stage 2 — Clarification Loop")

    if project["stages"]["stage2"] == "locked":
        st.info("🔒 This stage is locked. Complete and approve Stage 1 first.")
        st.stop()

    if project["stages"]["stage2"] == "complete":
        st.success("✅ Stage 2 has been approved and locked.")

    questions = project.get("clarification_questions", [])

    # ── Generate questions button ──
    if not questions:
        st.markdown("The AI will generate targeted questions based on gaps found in Stage 1.")

        if st.button("🤖 Generate Clarification Questions", type="primary"):
            with st.spinner("AI is generating questions based on the transcript gaps..."):
                result = api_call("POST", f"/projects/{project_id}/stage2/generate_questions")
                if result:
                    st.success(f"Generated {len(result)} questions!")
                    st.rerun()
    else:
        # Count answered/skipped/pending
        answered = sum(1 for q in questions if q.get("resolved") and not q.get("skipped"))
        skipped = sum(1 for q in questions if q.get("skipped"))
        pending = sum(1 for q in questions if not q.get("resolved") and not q.get("skipped"))

        st.markdown(f"**{len(questions)} questions** — {answered} answered · {skipped} skipped · {pending} pending")
        st.progress((answered + skipped) / len(questions))

        st.divider()

        # ── Display each question ──
        for q in questions:
            if q.get("resolved") and not q.get("skipped"):
                icon = "✅"
            elif q.get("skipped"):
                icon = "⏭️"
            else:
                icon = "❓"

            # Truncate long questions for the expander title
            short_q = q["question"][:70] + "..." if len(q["question"]) > 70 else q["question"]

            with st.expander(f"{icon} {short_q}"):
                st.markdown(f"**Full question:** {q['question']}")
                st.caption(f"📌 **Why this is being asked:** {q['reason']}")

                if q.get("skipped"):
                    st.warning(f"Skipped — Reason: {q.get('skip_reason', 'No reason given')}")

                elif q.get("resolved"):
                    st.success(f"**Answer:** {q.get('answer', '')}")
                    # Show follow-ups if any
                    for fu in q.get("follow_ups", []):
                        st.info(f"↳ **Follow-up:** {fu['question']}")
                        if fu.get("answer"):
                            st.success(f"  **Answer:** {fu['answer']}")

                else:
                    # Unanswered question — show answer form
                    answer_key = f"answer_{q['id']}"
                    answer_text = st.text_area(
                        "Your answer",
                        key=answer_key,
                        height=80,
                        placeholder="Type your answer here..."
                    )

                    col_submit, col_skip = st.columns([2, 1])

                    with col_submit:
                        if st.button(
                            "Submit Answer",
                            key=f"submit_{q['id']}",
                            type="primary",
                            disabled=not (answer_text or "").strip()
                        ):
                            with st.spinner("Processing answer..."):
                                result = api_call(
                                    "POST",
                                    f"/projects/{project_id}/stage2/answer/{q['id']}",
                                    json={"answer": answer_text.strip()}
                                )
                                if result:
                                    st.rerun()

                    with col_skip:
                        skip_reason = st.text_input(
                            "Skip reason",
                            key=f"skip_reason_{q['id']}",
                            placeholder="Why skipping?"
                        )
                        if st.button(
                            "Skip",
                            key=f"skip_{q['id']}",
                            disabled=not (skip_reason or "").strip()
                        ):
                            result = api_call(
                                "POST",
                                f"/projects/{project_id}/stage2/skip/{q['id']}",
                                json={"reason": skip_reason.strip()}
                            )
                            if result:
                                st.rerun()

        # ── User's own questions ──
        st.divider()
        st.subheader("💬 Ask Your Own Question")
        st.caption("Ask anything about the project — e.g. 'Can we fit the reporting module into Sprint 2?'")

        user_question = st.text_input(
            "Your question",
            placeholder="Ask anything about the project scope or plan...",
            key="user_question_input"
        )

        if st.button("Ask AI", disabled=not (user_question or "").strip()):
            with st.spinner("Thinking..."):
                result = api_call(
                    "POST",
                    f"/projects/{project_id}/stage2/ask",
                    json={"question": user_question.strip()}
                )
                if result:
                    st.info(f"**AI Answer:** {result['answer']}")

        # ── Approval ──
        st.divider()
        if project["stages"]["stage2"] != "complete":
            st.subheader("✅ Done with Clarification?")
            st.markdown("Click 'Done' when you've answered enough questions. You decide when to move on.")

            if st.button(
                "✅ Done — Proceed to Scope of Work",
                type="primary",
                use_container_width=True
            ):
                result = api_call("POST", f"/projects/{project_id}/stage2/approve")
                if result:
                    st.success("Stage 2 complete! Move to the Scope of Work tab.")
                    st.rerun()
        else:
            st.success("✅ Stage 2 approved and locked.")


# ════════════════════════════════════════════════════════════════
# TAB 3 — SCOPE OF WORK
# ════════════════════════════════════════════════════════════════
with tab3:
    st.header("Stage 3 — Scope of Work")

    if project["stages"]["stage3"] == "locked":
        st.info("🔒 This stage is locked. Complete and approve Stage 2 first.")
        st.stop()

    if project["stages"]["stage3"] == "complete":
        st.success("✅ Stage 3 has been approved and locked.")

    sow = project.get("scope_of_work")
    sow_version = project.get("sow_version", 0)

    # ── Generate SoW button ──
    if not sow:
        st.markdown("The AI will write a complete Scope of Work from the transcript, Q&A, and extraction.")
        if st.button("📝 Generate Scope of Work", type="primary"):
            with st.spinner("AI is writing your Scope of Work... (this takes 30-60 seconds)"):
                result = api_call("POST", f"/projects/{project_id}/stage3/generate")
                if result:
                    st.success("SoW generated!")
                    st.rerun()
    else:
        # Version badge
        col_title, col_badge, col_download = st.columns([3, 1, 1])
        with col_title:
            st.subheader(f"Scope of Work — Version {sow_version}")
        with col_badge:
            if sow_version == 1:
                st.warning("⚠️ First draft")
            else:
                st.success(f"✅ Revision {sow_version}")
        with col_download:
            st.download_button(
                label="📥 Download .md",
                data=sow,
                file_name=f"SoW_{project['name'].replace(' ', '_')}_v{sow_version}.md",
                mime="text/markdown",
                help="Download the Scope of Work as a Markdown file"
            )

        # Display the SoW in a scrollable box
        st.markdown(sow)

        # ── Feedback and revision ──
        st.divider()
        st.subheader("✏️ Provide Feedback for Revision")
        st.caption("The AI will revise the SoW and show you a changelog of every change made.")

        feedback_text = st.text_area(
            "Your feedback",
            height=120,
            placeholder=(
                "e.g. Add more detail to the GDPR compliance section. "
                "Remove Salesforce CRM from in-scope — it's explicitly out of scope. "
                "The Returns module deadline is 8 weeks from contract signing."
            ),
            key="sow_feedback"
        )

        if st.button(
            "Submit Feedback & Revise",
            disabled=not (feedback_text or "").strip(),
            type="primary"
        ):
            with st.spinner("AI is revising the SoW... (30-60 seconds)"):
                result = api_call(
                    "POST",
                    f"/projects/{project_id}/stage3/revise",
                    json={"feedback": feedback_text.strip()}
                )
                if result:
                    st.success(f"✅ Revised to Version {result['version']}")
                    st.subheader("📋 Changelog")
                    st.info(result["changelog"])
                    st.rerun()

        # ── Approval ──
        st.divider()
        if project["stages"]["stage3"] != "complete":
            if sow_version < 2:
                st.warning(
                    "⚠️ You must provide at least one round of feedback before approving. "
                    "This ensures the SoW has been reviewed, not just accepted as-is."
                )
                st.button(
                    "✅ Approve Scope of Work",
                    type="primary",
                    use_container_width=True,
                    disabled=True
                )
            else:
                st.subheader("✅ Approve the Scope of Work")
                if st.button(
                    "✅ Approve SoW & Unlock Sprint Planning",
                    type="primary",
                    use_container_width=True
                ):
                    result = api_call("POST", f"/projects/{project_id}/stage3/approve")
                    if result:
                        st.success("SoW approved! Move to the Sprint Plan tab.")
                        st.rerun()
        else:
            st.success("✅ Stage 3 approved and locked.")


# ════════════════════════════════════════════════════════════════
# TAB 4 — SPRINT PLANNING
# ════════════════════════════════════════════════════════════════
with tab4:
    st.header("Stage 4 — Task Breakdown & Sprint Planning")

    if project["stages"]["stage4"] == "locked":
        st.info("🔒 This stage is locked. Complete and approve Stage 3 first.")
        st.stop()

    if project["stages"]["stage4"] == "complete":
        st.success("✅ Stage 4 has been approved and locked.")

    tasks = project.get("tasks", [])
    sprints = project.get("sprints", [])

    # ── Generate sprint plan ──
    if not tasks:
        st.markdown("The AI will create a detailed task breakdown and sprint plan from the approved SoW.")
        if st.button("🗂️ Generate Sprint Plan", type="primary"):
            with st.spinner("AI is creating your sprint plan... (this takes 30-60 seconds)"):
                result = api_call("POST", f"/projects/{project_id}/stage4/generate")
                if result:
                    st.success(f"Generated {len(result['tasks'])} tasks across {len(result['sprints'])} sprints!")
                    st.rerun()
    else:
        # Summary metrics
        total_points = sum(s["total_points"] for s in sprints)
        over_limit_sprints = [s for s in sprints if s["total_points"] > 40]

        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("Total Tasks", len(tasks))
        col_m2.metric("Total Sprints", len(sprints))
        col_m3.metric("Total Points", total_points)
        col_m4.metric(
            "Over Limit",
            len(over_limit_sprints),
            delta=f"{len(over_limit_sprints)} sprint(s) need attention" if over_limit_sprints else "All good",
            delta_color="inverse"
        )

        if over_limit_sprints:
            st.warning(f"⚠️ {len(over_limit_sprints)} sprint(s) exceed 40 story points. Move some tasks to fix this.")

        st.divider()

        # ── Sprint tables ──
        st.subheader("Sprint Plan")
        for sprint in sprints:
            over = sprint["total_points"] > 40
            with st.expander(
                f"{'⚠️ ' if over else ''}**{sprint['name']}** — {sprint['total_points']} pts{' (OVER 40pt LIMIT)' if over else ''}",
                expanded=True
            ):
                st.caption(f"🎯 Sprint goal: {sprint['goal']}")

                # Get the tasks for this sprint
                sprint_task_ids = sprint.get("tasks", [])
                sprint_tasks = [t for t in tasks if t["id"] in sprint_task_ids]

                if sprint_tasks:
                    # Display as a table
                    import pandas as pd
                    df = pd.DataFrame([{
                        "ID": t["id"],
                        "Title": t["title"][:55] + ("..." if len(t["title"]) > 55 else ""),
                        "Type": t["type"],
                        "Priority": t["priority"],
                        "Points": t["story_points"],
                        "Module": t["module"],
                    } for t in sprint_tasks])
                    st.dataframe(df, use_container_width=True, hide_index=True)

                    # Expandable task details
                    with st.expander("View task details"):
                        for t in sprint_tasks:
                            st.markdown(f"**{t['id']}: {t['title']}**")
                            st.caption(t["description"])
                            if t.get("acceptance_criteria"):
                                st.markdown("Acceptance criteria:")
                                for ac in t["acceptance_criteria"]:
                                    st.markdown(f"  - {ac}")
                            if t.get("dependencies"):
                                st.caption(f"Dependencies: {', '.join(t['dependencies'])}")
                            st.divider()
                else:
                    st.caption("No tasks assigned to this sprint yet.")

        # ── Move task between sprints ──
        st.divider()
        st.subheader("🔀 Move a Task to a Different Sprint")

        col_task, col_sprint = st.columns(2)

        with col_task:
            task_options = {
                f"{t['id']}: {t['title'][:45]}": t["id"]
                for t in tasks
            }
            selected_task_label = st.selectbox(
                "Select task to move",
                options=list(task_options.keys()),
                key="move_task_select"
            )

        with col_sprint:
            # Build clean sprint name list
            sprint_name_options = []
            for s in sprints:
                clean = s["name"].replace("⚠️ OVER LIMIT — ", "").strip()
                sprint_name_options.append(clean)

            target_sprint = st.selectbox(
                "Move to sprint",
                options=sprint_name_options,
                key="move_sprint_select"
            )

        if st.button("Move Task ↔️"):
            task_id = task_options[selected_task_label]
            result = api_call(
                "POST",
                f"/projects/{project_id}/stage4/move_task",
                json={"task_id": task_id, "sprint": target_sprint}
            )
            if result:
                st.success(f"Moved task to {target_sprint}")
                st.rerun()

        # ── Approval ──
        st.divider()
        if project["stages"]["stage4"] != "complete":
            st.subheader("✅ Approve the Sprint Plan")
            if over_limit_sprints:
                st.warning("⚠️ You have sprints over the 40-point limit. Consider moving tasks before approving.")

            if st.button(
                "✅ Approve Sprint Plan & Unlock Jira Sync",
                type="primary",
                use_container_width=True
            ):
                result = api_call("POST", f"/projects/{project_id}/stage4/approve")
                if result:
                    st.success("Sprint plan approved! Move to the Jira Sync tab.")
                    st.rerun()
        else:
            st.success("✅ Stage 4 approved and locked.")


# ════════════════════════════════════════════════════════════════
# TAB 5 — JIRA SYNC
# ════════════════════════════════════════════════════════════════
with tab5:
    st.header("Stage 5 — Jira Sync")

    if project["stages"]["stage5"] == "locked":
        st.info("🔒 This stage is locked. Complete and approve Stage 4 first.")
        st.stop()

    jira_config = project.get("jira_config")
    jira_results = project.get("jira_results") or {}

    # ── Jira credentials setup ──
    st.subheader("🔗 Jira Connection Setup")

    with st.expander(
        "Configure Jira Credentials" + (" (configured ✅)" if jira_config else " (required)"),
        expanded=not jira_config
    ):
        import os
        from dotenv import load_dotenv
        load_dotenv()

        # Read values from .env automatically
        env_domain = os.getenv("JIRA_DOMAIN", "").replace("https://", "").strip("/")
        env_email  = os.getenv("JIRA_EMAIL", "")
        env_key    = os.getenv("JIRA_PROJECT_KEY", "")
        env_token  = os.getenv("JIRA_API_TOKEN", "")

        # Tell the user if .env values were found
        if env_domain:
            st.success("✅ Jira credentials loaded from your .env file — just click Test Connection")
        else:
            st.markdown("""
            **How to get your API token:**
            1. Go to [id.atlassian.com/manage-api-tokens](https://id.atlassian.com/manage-api-tokens)
            2. Click **Create API token**
            3. Give it a name, copy it immediately
            """)

        j_domain = st.text_input(
            "Jira domain",
            value=jira_config.get("domain", env_domain) if jira_config else env_domain,
            placeholder="yourcompany.atlassian.net"
        )
        j_email = st.text_input(
            "Your Jira email",
            value=jira_config.get("email", env_email) if jira_config else env_email,
            placeholder="you@company.com"
        )
        j_token = st.text_input(
            "API token",
            type="password",
            value=jira_config.get("api_token", env_token) if jira_config else env_token,
            placeholder="Loaded from .env automatically"
        )
        j_key = st.text_input(
            "Project key",
            value=jira_config.get("project_key", env_key) if jira_config else env_key,
            placeholder="e.g. MIS"
        )

        if st.button("🔌 Test Connection", type="primary"):
            if all([j_domain, j_email, j_token, j_key]):
                with st.spinner("Testing connection to Jira..."):
                    result = api_call(
                        "POST",
                        f"/projects/{project_id}/stage5/test_connection",
                        json={
                            "domain": j_domain,
                            "email": j_email,
                            "api_token": j_token,
                            "project_key": j_key,
                        }
                    )
                    if result and result.get("success"):
                        st.success(f"✅ Connected! Logged in as: **{result['user']}**")
                        st.rerun()
            else:
                st.warning("Please fill in all fields — or set them in your .env file")

    # ── Only show sync if connected ──
    if not jira_config:
        st.info("👆 Configure your Jira connection above to continue.")
        st.stop()

    st.divider()

    # ── Preview what will be created ──
    st.subheader("📊 Preview — What will be created in Jira")
    modules = project.get("stage1_output", {}).get("modules", [])
    tasks = project.get("tasks", [])
    sprints = project.get("sprints", [])

    col_p1, col_p2, col_p3 = st.columns(3)
    col_p1.metric("Epics to create", len(modules))
    col_p2.metric("Issues to create", len(tasks))
    col_p3.metric("Sprints to create", len(sprints))

    # ── Step-by-step push ──
    st.divider()
    st.subheader("🚀 Push to Jira — 3 Steps")
    st.caption("Complete each step in order. Each step shows a preview before pushing.")

    col1, col2, col3 = st.columns(3)

    # ── Step 1: Epics ──
    with col1:
        st.markdown("### Step 1 · Epics")
        st.caption("Creates one Epic per module")

        if "epic_map" not in jira_results:
            st.info(f"Will create {len(modules)} epics:")
            for m in modules:
                st.markdown(f"- {m['name']}")

            if st.button("Create Epics →", type="primary", use_container_width=True):
                with st.spinner(f"Creating {len(modules)} epics..."):
                    result = api_call("POST", f"/projects/{project_id}/stage5/push_epics")
                    if result:
                        st.success(f"✅ Created {len(result)} epics!")
                        st.rerun()
        else:
            st.success(f"✅ {len(jira_results['epic_map'])} epics created")
            for module_name, jira_key in jira_results["epic_map"].items():
                domain = jira_config.get("domain", "")
                st.markdown(
                    f"[{jira_key}](https://{domain}/browse/{jira_key}) — {module_name}"
                )

    # ── Step 2: Issues ──
    with col2:
        st.markdown("### Step 2 · Issues")
        st.caption("Creates one issue per task")

        if "epic_map" not in jira_results:
            st.info("⏸️ Complete Step 1 first")
        elif "issue_map" not in jira_results:
            st.info(f"Will create {len(tasks)} issues")

            if st.button("Create Issues →", type="primary", use_container_width=True):
                with st.spinner(f"Creating {len(tasks)} issues... (may take a while)"):
                    result = api_call("POST", f"/projects/{project_id}/stage5/push_issues")
                    if result:
                        st.success(f"✅ Created {len(result)} issues!")
                        st.rerun()
        else:
            st.success(f"✅ {len(jira_results['issue_map'])} issues created")
            # Show first 5 as sample
            items = list(jira_results["issue_map"].items())[:5]
            for task_id, jira_key in items:
                domain = jira_config.get("domain", "")
                st.markdown(f"[{jira_key}](https://{domain}/browse/{jira_key})")
            if len(jira_results["issue_map"]) > 5:
                st.caption(f"... and {len(jira_results['issue_map']) - 5} more")

    # ── Step 3: Sprints ──
    with col3:
        st.markdown("### Step 3 · Sprints")
        st.caption("Creates sprints and assigns issues")

        if "issue_map" not in jira_results:
            st.info("⏸️ Complete Step 2 first")
        elif not project.get("stage5_complete"):
            st.info(f"Will create {len(sprints)} sprints")

            if st.button("Create Sprints →", type="primary", use_container_width=True):
                with st.spinner("Creating sprints and assigning issues..."):
                    result = api_call("POST", f"/projects/{project_id}/stage5/push_sprints")
                    if result:
                        st.success(f"✅ Created {len(result)} sprints!")
                        st.balloons()
                        st.rerun()
        else:
            st.success("✅ All sprints created!")
            domain = jira_config.get("domain", "")
            project_key = jira_config.get("project_key", "")
            st.markdown(
                f"[Open project in Jira →](https://{domain}/jira/software/c/projects/{project_key}/list)"
            )

    # ── Completion message ──
    if project.get("stage5_complete"):
        st.divider()
        st.success("🎉 **Pipeline complete!** Everything has been pushed to Jira.")
        st.balloons()