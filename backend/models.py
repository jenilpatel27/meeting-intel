# backend/models.py
# These are Pydantic models — they define what our data looks like.
# Think of each class as a "form" with required fields and types.

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum


# --- Enums: limited choices (like a dropdown) ---

class Priority(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class StageStatus(str, Enum):
    LOCKED = "locked"      # User can't access yet
    ACTIVE = "active"      # Currently available
    COMPLETE = "complete"  # User has approved this stage


# --- Stage 1 data structures ---

class Module(BaseModel):
    name: str
    description: str
    priority: Priority = Priority.MEDIUM  # Default to Medium if AI returns something invalid
    deadline: Optional[str] = None

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    model_config = {"use_enum_values": True}


class Requirement(BaseModel):
    description: str
    module: str = "General"   # Default to "General" if AI returns null
    type: str = "Functional"  # Default to "Functional" if AI returns null
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class Integration(BaseModel):
    name: str
    description: str
    confidence: float = Field(ge=0.0, le=1.0)


class Constraint(BaseModel):
    description: str
    confidence: float = Field(ge=0.0, le=1.0)


class Assumption(BaseModel):
    description: str
    confidence: float = Field(ge=0.0, le=1.0)


class Unknown(BaseModel):
    description: str

# --- Stage 1 data structures --

class Stage1Output(BaseModel):
    """Everything the AI extracts from the transcript in Stage 1."""
    project_name: str
    client_name: str
    vendor_name: str
    modules: List[Module] = []
    requirements: List[Requirement] = []
    integrations: List[Integration] = []
    constraints: List[Constraint] = []
    assumptions: List[Assumption] = []
    unknowns: List[Unknown] = []


# --- Stage 2 data structures ---

class ClarificationQuestion(BaseModel):
    """One clarification question from Stage 2."""
    id: str
    question: str
    reason: str          # Why is this being asked — cites the transcript
    answer: Optional[str] = None
    resolved: bool = False
    skipped: bool = False
    skip_reason: Optional[str] = None
    follow_ups: List[Dict] = []


# --- Stage 4 data structures ---

class Task(BaseModel):
    """A single work task for the sprint plan."""
    id: str
    title: str
    description: str
    module: str
    type: str           # "Story", "Task", or "Epic"
    priority: Priority
    story_points: int   # Fibonacci: 1, 2, 3, 5, 8, 13
    dependencies: List[str] = []       # List of other task IDs
    acceptance_criteria: List[str] = []
    sprint: Optional[str] = None


class Sprint(BaseModel):
    """A 2-week sprint containing multiple tasks."""
    name: str
    goal: str
    tasks: List[str] = []    # List of task IDs
    total_points: int = 0


# --- Project stage tracking ---

class ProjectStages(BaseModel):
    """Tracks which stage is locked/active/complete for a project."""
    stage1: StageStatus = StageStatus.ACTIVE   # Stage 1 starts unlocked
    stage2: StageStatus = StageStatus.LOCKED
    stage3: StageStatus = StageStatus.LOCKED
    stage4: StageStatus = StageStatus.LOCKED
    stage5: StageStatus = StageStatus.LOCKED


# --- The main Project model ---

class Project(BaseModel):
    """Everything about one project. This is what gets saved to the database."""
    id: str
    name: str
    transcript: Optional[str] = None

    # Stage gate tracking
    stages: ProjectStages = ProjectStages()

    # Stage 1 data
    stage1_output: Optional[Stage1Output] = None
    stage1_approved: bool = False

    # Stage 2 data
    clarification_questions: List[ClarificationQuestion] = []
    stage2_approved: bool = False

    # Stage 3 data
    scope_of_work: Optional[str] = None
    sow_version: int = 0   # Tracks how many revisions have happened
    stage3_approved: bool = False

    # Stage 4 data
    tasks: List[Task] = []
    sprints: List[Sprint] = []
    stage4_approved: bool = False

    # Stage 5 data
    jira_config: Optional[Dict] = None    # Stores Jira connection details
    jira_results: Optional[Dict] = None  # Stores created Jira keys
    stage5_complete: bool = False

    # Metadata
    created_at: str
    updated_at: str

    