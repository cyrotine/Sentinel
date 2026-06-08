from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class IssueAnalysis(BaseModel):
    issue_type: str
    severity: str
    confidence: float
    impact: float


class PlanTask(BaseModel):
    id: str
    description: str
    depends_on: list[str] = Field(default_factory=list)


class Plan(BaseModel):
    tasks: list[PlanTask] = Field(default_factory=list)
    affected_files: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)


class CodeChange(BaseModel):
    file_path: str
    patch: str
    description: str


class TestResult(BaseModel):
    name: str
    passed: bool
    output: str = ""
    error: str | None = None


class Review(BaseModel):
    approved: bool
    comments: list[str] = Field(default_factory=list)
    security_issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class PullRequestDraft(BaseModel):
    title: str
    body: str
    branch: str
    base_branch: str = "main"


class WorkflowState(BaseModel):
    repository_id: str
    issue_id: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    error: str | None = None
    issue_analysis: IssueAnalysis | None = None
    plan: Plan | None = None
    code_changes: list[CodeChange] = Field(default_factory=list)
    test_results: list[TestResult] = Field(default_factory=list)
    review: Review | None = None
    pull_request_draft: PullRequestDraft | None = None
