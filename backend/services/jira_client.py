# backend/services/jira_client.py
# Handles all communication with the Jira REST API.
# Creates Epics, Issues (Stories/Tasks), and Sprints in Jira.

import requests
from requests.auth import HTTPBasicAuth
import time
from typing import Optional


class JiraClient:
    """
    A client for the Jira REST API.
    
    Usage:
        client = JiraClient("mycompany.atlassian.net", "me@email.com", "my-token", "MIS")
        client.test_connection()
        epic_key = client.create_epic("Returns Module", "Handles product returns")
    """

    def __init__(self, domain: str, email: str, api_token: str, project_key: str):
        # Remove https:// if user accidentally included it
        domain = domain.replace("https://", "").replace("http://", "").strip("/")

        self.base_url = f"https://{domain}/rest/api/3"
        self.agile_url = f"https://{domain}/rest/agile/1.0"
        self.auth = HTTPBasicAuth(email, api_token)
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        self.project_key = project_key

    def _request(self, method: str, url: str, **kwargs) -> dict:
        """
        Make an HTTP request to Jira with automatic rate-limit handling.
        
        If Jira says "slow down" (HTTP 429), we wait and retry up to 3 times.
        Raises an exception with a clear error message if the request fails.
        """
        for attempt in range(3):
            resp = requests.request(
                method, url,
                auth=self.auth,
                headers=self.headers,
                timeout=30,
                **kwargs
            )

            if resp.status_code == 429:
                # Rate limited — wait however long Jira says, then retry
                wait_seconds = int(resp.headers.get("Retry-After", 10))
                print(f"Rate limited. Waiting {wait_seconds} seconds...")
                time.sleep(wait_seconds)
                continue

            if not resp.ok:
                # Parse Jira's error message if available
                try:
                    error_data = resp.json()
                    error_msg = error_data.get("errorMessages", [str(resp.status_code)])
                    errors = error_data.get("errors", {})
                    raise Exception(f"Jira API error {resp.status_code}: {error_msg} {errors}")
                except Exception as e:
                    if "Jira API error" in str(e):
                        raise
                    raise Exception(f"Jira API error {resp.status_code}: {resp.text[:200]}")

            return resp.json() if resp.content else {}

        raise Exception("Failed after 3 attempts due to rate limiting")

    def test_connection(self) -> dict:
        """
        Test that the credentials work by fetching the current user's info.
        Returns: {"success": True, "user": "John Smith"}
        """
        result = self._request("GET", f"{self.base_url}/myself")
        return {
            "success": True,
            "user": result.get("displayName", result.get("emailAddress", "Unknown"))
        }

    def create_epic(self, name: str, description: str) -> str:
        """
        Create an Epic in Jira and return its issue key (e.g., "MIS-1").
        Epics group related stories/tasks together.
        """
        data = {
            "fields": {
                "project": {"key": self.project_key},
                "summary": name,
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [{
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description}]
                    }]
                },
                "issuetype": {"name": "Epic"},
                "customfield_10011": name,   # "Epic Name" custom field
            }
        }
        result = self._request("POST", f"{self.base_url}/issue", json=data)
        return result["key"]

    def create_issue(
        self,
        title: str,
        description: str,
        issue_type: str,
        priority: str,
        story_points: int,
        epic_key: Optional[str],
        acceptance_criteria: list
    ) -> str:
        """
        Create a Story or Task in Jira and return its issue key (e.g., "MIS-5").
        
        epic_key: The Jira key of the parent Epic (e.g., "MIS-1")
        """
        # Append acceptance criteria to the description
        ac_text = "\n".join([f"• {ac}" for ac in acceptance_criteria])
        full_description = f"{description}\n\nAcceptance Criteria:\n{ac_text}"

        # Map our priority names to Jira's expected values
        priority_map = {"High": "High", "Medium": "Medium", "Low": "Low"}
        jira_priority = priority_map.get(priority, "Medium")

        data = {
            "fields": {
                "project": {"key": self.project_key},
                "summary": title,
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [{
                        "type": "paragraph",
                        "content": [{"type": "text", "text": full_description}]
                    }]
                },
                "issuetype": {"name": issue_type if issue_type in ["Story", "Task", "Bug"] else "Story"},
                "priority": {"name": jira_priority},
                "customfield_10016": story_points,
            }
        }

        # Link to parent Epic if provided
        if epic_key:
            data["fields"]["customfield_10014"] = epic_key   # Epic Link field

        result = self._request("POST", f"{self.base_url}/issue", json=data)
        return result["key"]

    def get_board_id(self) -> Optional[int]:
        """
        Find the Scrum board ID for our project.
        Needed before we can create sprints.
        Returns None if no board is found.
        """
        result = self._request(
            "GET",
            f"{self.agile_url}/board?projectKeyOrId={self.project_key}&type=scrum"
        )
        boards = result.get("values", [])
        if boards:
            return boards[0]["id"]
        # Try without the type filter
        result2 = self._request("GET", f"{self.agile_url}/board?projectKeyOrId={self.project_key}")
        boards2 = result2.get("values", [])
        return boards2[0]["id"] if boards2 else None

    def create_sprint(self, board_id: int, name: str, goal: str) -> int:
        """
        Create a sprint on the given board and return its sprint ID.
        Jira enforces a 30 character max on sprint names.
        """
        # Truncate to 29 chars to stay under Jira's 30 char limit
        truncated_name = name[:29].strip() if len(name) > 29 else name

        data = {
            "name": truncated_name,
            "goal": goal,
            "originBoardId": board_id
        }
        result = self._request("POST", f"{self.agile_url}/sprint", json=data)
        return result["id"]

    def add_issues_to_sprint(self, sprint_id: int, issue_keys: list[str]):
        """
        Move a list of Jira issues into a specific sprint.
        issue_keys example: ["MIS-5", "MIS-6", "MIS-7"]
        """
        self._request(
            "POST",
            f"{self.agile_url}/sprint/{sprint_id}/issue",
            json={"issues": issue_keys}
        )