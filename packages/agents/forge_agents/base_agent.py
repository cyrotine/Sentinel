from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from forge_workflows.state import WorkflowState


class AgentResult(BaseModel):
    success: bool
    error: str | None = None


class BaseAgent(ABC):
    name: str

    @abstractmethod
    async def run(self, state: WorkflowState) -> AgentResult: ...
