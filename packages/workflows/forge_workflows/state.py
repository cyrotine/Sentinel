"""Sentinel Brain workflow state definitions.

This module defines the complete state that flows through the LangGraph
multi-agent pipeline.  Every agent reads from and writes to fields on
:class:`SentinelState`.

Design principles:
    - Existing models (``IssueAnalysis``, ``Plan``, ``CodeChange``, etc.) are
      preserved and extended only where the Brain requires additional context.
    - ``WorkflowState`` is kept as a backward-compatible alias so that
      ``graph.py`` and ``base_agent.py`` continue to work without changes.
    - New models are added for capabilities that did not exist before:
      ``RepoContext``, ``SelectedIssue``, ``RetrievedChunk``, ``ValidationResult``.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class WorkflowStatus(str, Enum):
    """Coarse lifecycle status for a workflow run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SentinelStatus(str, Enum):
    """Fine-grained status for Sentinel Brain runs.

    Extends the original ``WorkflowStatus`` values with per-agent tracking
    so the API can report exactly which stage the pipeline has reached.
    """

    PENDING = "pending"
    ANALYZING_REPO = "analyzing_repo"
    ANALYZING_ISSUES = "analyzing_issues"
    PRIORITIZING = "prioritizing"
    RETRIEVING_CONTEXT = "retrieving_context"
    PLANNING = "planning"
    DEVELOPING = "developing"
    VALIDATING = "validating"
    TESTING = "testing"
    REVIEWING = "reviewing"
    GENERATING_PR = "generating_pr"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Existing models — preserved, extended where noted
# ---------------------------------------------------------------------------


class IssueAnalysis(BaseModel):
    """Structured analysis of a single GitHub issue.

    Produced by the Issue Analyzer agent for every candidate issue.

    The original four fields (``issue_type``, ``severity``, ``confidence``,
    ``impact``) are retained.  New fields provide richer context that
    downstream agents (prioritizer, planner) rely on.
    """

    # --- original fields (unchanged) ---
    issue_type: str = Field(
        ..., description="Classification: bug, feature, refactor, docs, test, chore"
    )
    severity: str = Field(
        ..., description="Severity level: critical, high, medium, low"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Model confidence in this analysis (0-1)"
    )
    impact: float = Field(
        ..., ge=0.0, le=1.0, description="Estimated impact on the project (0-1)"
    )

    # --- new fields for Sentinel Brain ---
    issue_id: str = Field(
        default="", description="Internal UUID of the issue row in Postgres"
    )
    number: int = Field(
        default=0, description="GitHub issue number (e.g. 42)"
    )
    title: str = Field(
        default="", description="Issue title for downstream reference"
    )
    body: str = Field(
        default="", description="Issue body/description"
    )
    affected_areas: list[str] = Field(
        default_factory=list,
        description="File paths or module names likely affected by this issue",
    )
    reasoning: str = Field(
        default="",
        description="Free-text explanation of how the analysis was derived",
    )


class PlanTask(BaseModel):
    """A single task within an implementation plan.

    Tasks form a DAG via ``depends_on`` references to other task IDs.
    """

    id: str = Field(..., description="Unique task identifier within the plan")
    description: str = Field(..., description="What this task accomplishes")
    depends_on: list[str] = Field(
        default_factory=list,
        description="IDs of tasks that must complete before this one",
    )


class Plan(BaseModel):
    """Implementation plan produced by the Planner agent.

    The original three fields are retained.  ``approach_reasoning``
    captures *why* this approach was chosen over alternatives.
    """

    tasks: list[PlanTask] = Field(default_factory=list)
    affected_files: list[str] = Field(
        default_factory=list,
        description="Relative file paths that will be created or modified",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="External packages or internal modules this plan depends on",
    )
    approach_reasoning: str = Field(
        default="",
        description="Explanation of the chosen approach and alternatives considered",
    )


class CodeChange(BaseModel):
    """A single file modification produced by the Developer agent."""

    file_path: str = Field(..., description="Relative path from repo root")
    patch: str = Field(..., description="Unified diff or full replacement content")
    description: str = Field(
        ..., description="Human-readable summary of what changed and why"
    )


class TestResult(BaseModel):
    """Result of a single test case, produced by the Test agent."""

    name: str = Field(..., description="Test name or identifier")
    passed: bool = Field(..., description="Whether the test passed")
    output: str = Field(default="", description="Stdout/stderr from the test run")
    error: str | None = Field(
        default=None, description="Error message if the test failed"
    )


class Review(BaseModel):
    """Code review produced by the Reviewer agent."""

    approved: bool = Field(
        ..., description="Whether the reviewer approves the changes"
    )
    comments: list[str] = Field(
        default_factory=list, description="General review comments"
    )
    security_issues: list[str] = Field(
        default_factory=list, description="Identified security concerns"
    )
    suggestions: list[str] = Field(
        default_factory=list,
        description="Actionable improvement suggestions for the developer",
    )


class PullRequestDraft(BaseModel):
    """PR metadata produced by the PR Generator agent."""

    title: str = Field(..., description="Pull request title")
    body: str = Field(..., description="Markdown body with context, changes, and testing notes")
    branch: str = Field(..., description="Source branch name")
    base_branch: str = Field(default="main", description="Target branch")


# ---------------------------------------------------------------------------
# New models for Sentinel Brain
# ---------------------------------------------------------------------------


class RepoContext(BaseModel):
    """High-level understanding of a repository's structure and technology.

    Produced by the Repository Analyzer agent.  Gives every downstream agent
    a shared understanding of what they are working with.
    """

    repository_name: str = Field(
        default="", description="Repository name (owner/name)"
    )
    description: str = Field(
        default="", description="Repository description from GitHub"
    )
    languages: list[str] = Field(
        default_factory=list,
        description="Programming languages detected in the repository",
    )
    framework_hints: list[str] = Field(
        default_factory=list,
        description="Frameworks and libraries detected (e.g. FastAPI, React, Django)",
    )
    total_files: int = Field(
        default=0, description="Total number of source files"
    )
    key_files: list[str] = Field(
        default_factory=list,
        description="Important files like README, main entry points, config files",
    )
    detected_modules: list[str] = Field(
        default_factory=list,
        description="Logical modules or packages identified in the codebase",
    )
    architecture_summary: str = Field(
        default="",
        description="Natural-language summary of the repository's architecture",
    )


class SelectedIssue(BaseModel):
    """The issue chosen by the Issue Prioritizer agent for implementation.

    Contains the full issue content plus the reasoning behind the selection,
    so downstream agents never need to re-query the issue data.
    """

    issue_id: str = Field(..., description="Internal UUID of the selected issue")
    number: int = Field(..., description="GitHub issue number")
    title: str = Field(..., description="Issue title")
    body: str = Field(default="", description="Full issue body/description")
    reasoning: str = Field(
        default="",
        description="Why this issue was selected over others",
    )
    estimated_complexity: str = Field(
        default="medium",
        description="Estimated implementation complexity: low, medium, high",
    )


class RetrievedChunk(BaseModel):
    """A code chunk retrieved from Qdrant via semantic search.

    Populated by the ``retrieve_context`` utility node (not an agent).
    Provides the relevant source code that agents use for planning
    and code generation.
    """

    file_path: str = Field(..., description="Relative file path in the repository")
    content: str = Field(..., description="Source code content of the chunk")
    start_line: int = Field(..., description="First line number of the chunk")
    end_line: int = Field(..., description="Last line number of the chunk")
    language: str = Field(default="", description="Programming language of the file")
    score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Cosine similarity score from Qdrant (0-1)",
    )


class ValidationResult(BaseModel):
    """Output of the Validator agent's code review.

    A lightweight check that runs before the full Reviewer agent.
    Catches obvious issues (syntax errors, missing imports, plan
    misalignment) so the developer can fix them before review.
    """

    passed: bool = Field(
        ..., description="Whether the code changes passed validation"
    )
    issues: list[str] = Field(
        default_factory=list,
        description="Specific problems found in the generated code",
    )
    suggestions: list[str] = Field(
        default_factory=list,
        description="Actionable fixes the developer should apply",
    )


# ---------------------------------------------------------------------------
# SentinelState — the central workflow state
# ---------------------------------------------------------------------------


class SentinelState(BaseModel):
    """Complete state for a Sentinel Brain workflow run.

    This is the single object that flows through the LangGraph pipeline.
    Each agent reads the fields it needs and writes its output fields.
    Fields are ordered by the pipeline phase that produces them.

    Phase 1 — Understand:  repo_context, issue_analyses
    Phase 2 — Decide:      selected_issue
    Phase 3 — Retrieve:    relevant_chunks
    Phase 4 — Plan:        plan
    Phase 5 — Execute:     code_changes
    Phase 6 — Validate:    validation_result, test_results, review
    Phase 7 — Ship:        pull_request_draft
    """

    # --- Inputs (set when the workflow is created) ---

    repository_id: str = Field(
        ..., description="UUID of the repository in Postgres"
    )
    target_issue_id: str | None = Field(
        default=None,
        description="Specific issue to work on.  None = let the Brain select.",
    )

    # --- Phase 1: Understand (repo_analyzer, issue_analyzer) ---

    repo_context: RepoContext | None = Field(
        default=None, description="Repository understanding from the Repo Analyzer agent"
    )
    issue_analyses: list[IssueAnalysis] = Field(
        default_factory=list,
        description="Analysis results for each candidate issue",
    )

    # --- Phase 2: Decide (issue_prioritizer) ---

    selected_issue: SelectedIssue | None = Field(
        default=None, description="The issue chosen for implementation"
    )

    # --- Phase 3: Retrieve (retrieve_context utility node) ---

    relevant_chunks: list[RetrievedChunk] = Field(
        default_factory=list,
        description="Code chunks from Qdrant relevant to the selected issue",
    )

    # --- Phase 4: Plan (planner) ---

    plan: Plan | None = Field(
        default=None, description="Implementation plan from the Planner agent"
    )

    # --- Phase 5: Execute (developer) ---

    code_changes: list[CodeChange] = Field(
        default_factory=list,
        description="File modifications produced by the Developer agent",
    )

    # --- Phase 6: Validate (validator, test_agent, reviewer) ---

    validation_result: ValidationResult | None = Field(
        default=None, description="Output of the Validator agent"
    )
    test_results: list[TestResult] = Field(
        default_factory=list,
        description="Test outcomes from the Test agent",
    )
    review: Review | None = Field(
        default=None, description="Code review from the Reviewer agent"
    )

    # --- Phase 7: Ship (pr_generator) ---

    pull_request_draft: PullRequestDraft | None = Field(
        default=None, description="Final PR metadata from the PR Generator agent"
    )

    # --- Workflow metadata ---

    status: SentinelStatus = Field(
        default=SentinelStatus.PENDING,
        description="Current pipeline stage",
    )
    current_agent: str = Field(
        default="", description="Name of the agent currently executing"
    )
    error: str | None = Field(
        default=None, description="Error message if the workflow failed"
    )
    iteration: int = Field(
        default=0,
        description="Current developer↔reviewer loop iteration (0-indexed)",
    )
    max_iterations: int = Field(
        default=3,
        description="Maximum developer↔reviewer retry loops before forcing completion",
    )


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------

# graph.py and base_agent.py import WorkflowState.
# Keep it as an alias so those modules work without modification.
WorkflowState = SentinelState
