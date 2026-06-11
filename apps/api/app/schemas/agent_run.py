from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AgentRunCreate(BaseModel):
    repository_id: uuid.UUID
    target_issue_id: uuid.UUID


class AgentRunCreatedOut(BaseModel):
    run_id: uuid.UUID
    status: str


class AgentRunResult(BaseModel):
    """Serialized subset of the final SentinelState, stored in agent_runs.result."""

    selected_issue: dict | None = None
    plan: dict | None = None
    code_changes: list[dict] = []
    review: dict | None = None
    pull_request_draft: dict | None = None
    pull_request_url: str | None = None
    pull_request_number: int | None = None
    iteration: int | None = None
    repair_context: dict | None = None


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repository_id: uuid.UUID
    target_issue_id: uuid.UUID | None
    status: str
    current_node: str | None
    error: str | None
    result: AgentRunResult | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class AgentRunListOut(BaseModel):
    total: int
    runs: list[AgentRunOut]