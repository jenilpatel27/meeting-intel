# backend/pipeline/stage4_sprint.py
# Stage 4: Generate tasks and organize them into sprints.
# The AI reads the approved SoW and creates a Fibonacci-pointed sprint plan.

from backend.services.llm import run_json_prompt
from backend.models import Stage1Output, Task, Sprint, Priority


MAX_SPRINT_POINTS = 40   # Warn if a sprint exceeds this
SPRINT_WEEKS = 2         # Each sprint is 2 weeks


def generate_tasks_and_sprints(
    sow: str,
    stage1: Stage1Output
) -> tuple[list[Task], list[Sprint]]:
    """
    Read the approved Scope of Work and generate:
    1. A list of Task objects (stories, tasks, epics)
    2. A list of Sprint objects organizing those tasks
    
    Rules enforced:
    - Story points must be Fibonacci (1, 2, 3, 5, 8, 13)
    - Max 40 points per sprint
    - Dependencies respected
    - Sprint names reflect their goal
    """

    module_names = [m.name for m in stage1.modules]

    result = run_json_prompt(
        system="""You are a senior scrum master creating a detailed sprint plan from a Scope of Work.

STRICT RULES:
1. Story points MUST be exactly one of: 1, 2, 3, 5, 8, 13 (Fibonacci only)
2. Max 40 story points per sprint
3. Sprint names MUST reflect the goal AND be under 30 characters total (e.g. "Sprint 1 - Core Setup", "Sprint 2 - Dashboard")
4. High-priority / earliest-deadline modules go in Sprint 1
5. Dependencies must be respected (a task cannot be in an earlier sprint than its dependency)
6. Every task needs at least 2 acceptance criteria
7. Titles must be action-oriented (e.g. "Build returns submission form" not "Returns form")""",

        user=f"""Scope of Work:
{sow[:5000]}

Module names: {module_names}

Generate the complete sprint plan as JSON:
{{
  "tasks": [
    {{
      "id": "T001",
      "title": "action-oriented title starting with a verb",
      "description": "2-3 sentence description of what needs to be built",
      "module": "exact module name from the list above",
      "type": "Story or Task or Epic",
      "priority": "High or Medium or Low",
      "story_points": 1,
      "dependencies": [],
      "acceptance_criteria": [
        "First acceptance criterion",
        "Second acceptance criterion"
      ],
      "sprint": "Sprint 1 — Returns Core"
    }}
  ],
  "sprints": [
    {{
      "name": "Sprint 1 — Returns Core",
      "goal": "One sentence describing what this sprint achieves",
      "tasks": ["T001", "T002"],
      "total_points": 28
    }}
  ]
}}"""
    )

    tasks = [Task(**t) for t in result["tasks"]]
    sprints = [Sprint(**s) for s in result["sprints"]]

    # Add warning prefix to sprints that are over the point limit
    for sprint in sprints:
        if sprint.total_points > MAX_SPRINT_POINTS:
            sprint.name = f"⚠️ OVER LIMIT — {sprint.name}"

    return tasks, sprints


def move_task_to_sprint(
    tasks: list[Task],
    task_id: str,
    new_sprint: str
) -> list[Task]:
    """
    Move a task from one sprint to another.
    Called when the user drags/moves a task in the UI.
    """
    for task in tasks:
        if task.id == task_id:
            task.sprint = new_sprint
            break
    return tasks


def recalculate_sprint_points(
    tasks: list[Task],
    sprints: list[Sprint]
) -> list[Sprint]:
    """
    After moving tasks around, recalculate total story points for each sprint.
    Adds warning prefix if a sprint goes over 40 points.
    """
    for sprint in sprints:
        # Clean sprint name (remove any previous warning)
        clean_name = sprint.name.replace("⚠️ OVER LIMIT — ", "")

        # Count points for tasks in this sprint
        sprint.tasks = [t.id for t in tasks if t.sprint == clean_name or t.sprint == sprint.name]
        sprint.total_points = sum(
            t.story_points for t in tasks
            if t.sprint == clean_name or t.sprint == sprint.name
        )

        # Re-apply or remove warning
        if sprint.total_points > MAX_SPRINT_POINTS:
            sprint.name = f"⚠️ OVER LIMIT — {clean_name}"
        else:
            sprint.name = clean_name

    return sprints