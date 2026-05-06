# backend/pipeline/stage5_jira.py
# Stage 5: Orchestrates the Jira sync process.
# This thin layer calls JiraClient and tracks what's been created.

from backend.services.jira_client import JiraClient
from backend.models import Project


def push_epics(project: Project) -> list[dict]:
    """
    Create one Jira Epic for each module in the project.
    Returns a list of {module: name, jira_key: "MIS-1"} dicts.
    """
    cfg = project.jira_config
    client = JiraClient(cfg["domain"], cfg["email"], cfg["api_token"], cfg["project_key"])

    results = []
    epic_map = {}   # module_name -> jira_epic_key

    for module in project.stage1_output.modules:
        print(f"Creating epic for module: {module.name}")
        key = client.create_epic(module.name, module.description)
        epic_map[module.name] = key
        results.append({"module": module.name, "jira_key": key})

    return results, epic_map


def push_issues(project: Project, epic_map: dict) -> list[dict]:
    """
    Create one Jira issue for each task in the sprint plan.
    Links each issue to its parent Epic.
    Returns a list of {task_id, title, jira_key} dicts.
    """
    cfg = project.jira_config
    client = JiraClient(cfg["domain"], cfg["email"], cfg["api_token"], cfg["project_key"])

    results = []
    issue_map = {}  # task_id -> jira_issue_key

    for task in project.tasks:
        epic_key = epic_map.get(task.module)
        print(f"Creating issue: {task.title}")
        key = client.create_issue(
            title=task.title,
            description=task.description,
            issue_type=task.type,
            priority=task.priority,
            story_points=task.story_points,
            epic_key=epic_key,
            acceptance_criteria=task.acceptance_criteria,
        )
        issue_map[task.id] = key
        results.append({"task_id": task.id, "title": task.title, "jira_key": key})

    return results, issue_map


def push_sprints(project: Project, issue_map: dict) -> list[dict]:
    """
    Create sprints in Jira and add the correct issues to each sprint.
    Returns a list of {sprint_name, jira_sprint_id, issues} dicts.
    """
    cfg = project.jira_config
    client = JiraClient(cfg["domain"], cfg["email"], cfg["api_token"], cfg["project_key"])

    board_id = client.get_board_id()
    if not board_id:
        raise Exception(
            "No Scrum board found for this project. "
            "Make sure your Jira project has a Scrum board configured."
        )

    results = []

    for sprint in project.sprints:
        # Clean the sprint name (remove any warning prefixes we added)
        clean_name = sprint.name.replace("⚠️ OVER LIMIT — ", "").strip()

        print(f"Creating sprint: {clean_name}")
        sprint_id = client.create_sprint(board_id, clean_name, sprint.goal)

        # Collect the Jira issue keys for all tasks in this sprint
        issue_keys = []
        for task_id in sprint.tasks:
            jira_key = issue_map.get(task_id)
            if jira_key:
                issue_keys.append(jira_key)

        if issue_keys:
            client.add_issues_to_sprint(sprint_id, issue_keys)

        results.append({
            "sprint": clean_name,
            "jira_sprint_id": sprint_id,
            "issues": issue_keys
        })

    return results