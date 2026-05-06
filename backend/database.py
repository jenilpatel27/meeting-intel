# backend/database.py
# This file handles saving and loading projects from a local SQLite database.
# SQLite = a database that lives in a single file (data/projects.db).
# No server needed — Python reads/writes it directly.

import sqlite3
import json
from datetime import datetime
from typing import List, Optional
from pathlib import Path

from backend.models import Project


# Path to the database file — it will be auto-created
DB_PATH = Path("data/projects.db")


def get_connection():
    """Open a connection to the SQLite database file."""
    # Create the 'data' folder if it doesn't exist yet
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    # This makes rows behave like dicts (row["id"] instead of row[0])
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the projects table if it doesn't already exist.
    Called once when the server starts up."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                data        TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            )
        """)
        conn.commit()


def save_project(project: Project):
    """Save a project to the database.
    If it already exists (same id), it gets replaced.
    We store the entire project as a JSON string in the 'data' column."""
    project.updated_at = datetime.now().isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO projects (id, name, data, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                project.id,
                project.name,
                project.model_dump_json(),   # Converts the Pydantic model to JSON string
                project.created_at,
                project.updated_at,
            )
        )
        conn.commit()


def load_project(project_id: str) -> Optional[Project]:
    """Load a project from the database by its ID.
    Returns None if not found."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT data FROM projects WHERE id = ?", (project_id,)
        ).fetchone()

    if row:
        # Convert the JSON string back into a Project object
        return Project.model_validate_json(row["data"])
    return None


def list_projects() -> List[dict]:
    """Return a list of all projects (just id, name, updated_at — not full data)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, name, updated_at FROM projects ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def delete_project(project_id: str):
    """Permanently delete a project from the database."""
    with get_connection() as conn:
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
        