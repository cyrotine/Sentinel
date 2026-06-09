# Spec: Simplify Code Structure & Incorporate Packages Logic

## Overview

The `packages/` layer (agents, workflows, vector-store, repository-analysis) contains complete, production-ready logic, but it is not yet integrated into the `apps/api/` service layer in a clean way. The current connection point — `packages/workflows/forge_workflows/graph.py` — embeds raw database queries, inline `import` statements inside async node functions, and direct `app.*` coupling inside a package that is supposed to be application-agnostic.

This feature:

1. **Decouples** the LangGraph graph nodes from `apps/api` internals by introducing a `BrainService` in `apps/api/app/services/` that owns the database I/O and passes pre-loaded data into the pure agents.
2. **Adds a `AgentRun` database model** to track pipeline execution status and results persistently.
3. **Exposes the pipeline over HTTP** via a `POST /api/agent-runs` endpoint so the frontend and external clients can trigger and monitor runs.
4. **Cleans up `graph.py`** by removing all inline imports and all direct database access from node functions — nodes receive their data via `SentinelState` fields that are populated before the graph is invoked.
5. **Introduces a `Depends`-injectable `BrainContext`** struct that holds the LLM, embedder, and vector-store instances so they are constructed once per request rather than inside every node.

This directly advances the "Act" capability: it is the wire that connects the autonomous reasoning pipeline to the API surface.

---

## Depends On

- `01-generate-skeleton` — monorepo scaffolding
- `02-repository-ingestion` — `Repository`, `RepositoryFile`, `Issue` models and repos

---

## User Story

As a Forge developer, I want a single clean `BrainService.run(repository_id, target_issue_id?)` call that triggers the full LangGraph pipeline, persists the run state to PostgreSQL, and returns a run ID — so that the API layer stays thin, packages stay portable, and future agents can be tested in isolation without pulling in the entire application context.

---

## Agent Changes

### Modify

**All graph node functions in `packages/workflows/forge_workflows/graph.py`**

Current state: Each node contains inline `import` statements for `app.*`, constructs its own LLM instance, and queries the database directly.

Required change: Nodes become **pure state transformers**. They receive all required data via `SentinelState` fields that are populated before graph execution. The LLM, embedder, and vector-store are passed in via `SentinelState.context` (a new optional `BrainContext` field), or injected at graph-construction time through node closures.

Affected nodes:
- `repo_analyzer` — remove DB queries; receive `file_paths`, `file_languages`, `total_files`, `repo_name`, `repo_description` from state
- `issue_analyzer` — remove DB queries; receive `raw_issues: list[dict]` from state
- `issue_prioritizer` — already pure after prior node populates `issue_analyses`; remove LLM construction → use injected LLM
- `retrieve_context` — remove inline imports; use injected `embedder` + `vector_store`
- `planner`, `developer`, `validator`, `test_agent`, `reviewer`, `pr_generator` — remove LLM construction in each node; use injected LLM

**Pattern for LLM injection:**

```python
# graph.py — build_graph() receives dependencies at construction time
def build_graph(llm, embedder, vector_store) -> StateGraph:
    async def repo_analyzer(state: SentinelState) -> dict:
        agent = RepoAnalyzerAgent(llm=llm)
        ...
```

This eliminates 10× duplicated `ChatGoogleGenerativeAI(...)` constructions and all inline `from app.config import settings` / `from langchain_google_genai import ...` inside node closures.

---

## Workflow Changes

### Inputs

`SentinelState` gains two pre-loaded fields populated by `BrainService` before graph invocation:

```python
raw_issues: list[dict]  # pre-loaded from DB by BrainService
collection_name: str    # Qdrant collection name for this repo
```

The `repo_context` and `relevant_chunks` fields already exist in `SentinelState`; they are now populated inside the graph by pure agent calls.

### Outputs

`SentinelState` gains one new field:

```python
agent_run_id: str  # UUID of the AgentRun DB record, set by BrainService before invocation
```

### State Changes

**New fields added to `SentinelState`:**

```python
raw_issues: list[dict] = Field(default_factory=list)
collection_name: str = Field(default="")
agent_run_id: str = Field(default="")
```

**No removals** — all existing fields preserved.

### Graph Nodes

All 10 existing nodes are kept. Their signatures do not change (`async def node(state: SentinelState) -> dict`). Their bodies are cleaned of inline imports and DB queries.

### Graph Edges

No edge changes. The topology is unchanged.

---

## Database Changes

### Create

**Table: `agent_runs`**

| Column | Type | Notes |
|---|---|---|
| `id` | `UUID` PK | |
| `repository_id` | `UUID` FK → `repositories.id` | CASCADE DELETE |
| `target_issue_id` | `UUID` nullable | user-specified override |
| `status` | `VARCHAR(32)` | mirrors `SentinelStatus` enum values |
| `current_node` | `VARCHAR(64)` nullable | last node that completed |
| `error` | `TEXT` nullable | failure message |
| `result` | `JSONB` nullable | serialized final `SentinelState` fields (pr draft, plan, review) |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | |
| `started_at` | `TIMESTAMP WITH TIME ZONE` nullable | |
| `completed_at` | `TIMESTAMP WITH TIME ZONE` nullable | |

Alembic migration required.

### Modify

No existing tables modified.

---

## Retrieval Changes

No new Qdrant collections or embedding logic. `collection_name` is computed deterministically as `repo_{repository_id}` (already the convention in the ingestion service) and passed into `SentinelState` by `BrainService` before graph invocation.

---

## API Changes

### New Router

**File:** `apps/api/app/api/agent_runs.py`

Replace the stub `apps/api/app/api/agents.py` from spec 03 with this fully wired router.

---

#### `POST /api/agent-runs`

Trigger a new pipeline run.

Request:
```json
{
  "repository_id": "uuid",
  "target_issue_id": "uuid | null"
}
```

Response `202 Accepted`:
```json
{
  "run_id": "uuid",
  "status": "pending"
}
```

Behavior: creates an `AgentRun` DB record with status `pending`, fires `brain_service.start(run_id)` as a background task.

---

#### `GET /api/agent-runs`

List runs, optionally filtered.

Query params: `repository_id: str | None`, `limit: int = 20`, `offset: int = 0`

Response:
```json
{
  "total": 1,
  "runs": [AgentRunOut]
}
```

---

#### `GET /api/agent-runs/{run_id}`

Get a single run with full result.

Response: `AgentRunOut` (includes `result` field when completed).

---

### New Pydantic Schemas

**File:** `apps/api/app/schemas/agent_run.py`

```python
class AgentRunCreate(BaseModel):
    repository_id: uuid.UUID
    target_issue_id: uuid.UUID | None = None

class AgentRunCreatedOut(BaseModel):
    run_id: uuid.UUID
    status: str

class AgentRunResult(BaseModel):
    pull_request_draft: dict | None = None
    plan: dict | None = None
    review: dict | None = None
    code_changes: list[dict] = []

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
```

---

## Frontend Changes

### Pages

**`apps/web/src/app/agents/page.tsx`** — replace stub with real server component that fetches `GET /api/agent-runs` and renders a list of runs with status badges.

**`apps/web/src/app/agents/[runId]/page.tsx`** — replace stub with real server component showing run details: current node, plan summary, code changes count, PR draft title, review outcome.

### Components

**`apps/web/src/components/agents/`**

```
agents-page.tsx           — list of AgentRunOut with status, timestamps, repo name
agent-run-detail.tsx      — single run: progress indicator, plan tasks, code changes, PR draft
start-agent-run-button.tsx — client component: POST /api/agent-runs → redirect to /agents/:runId
```

### API Client (`apps/web/src/lib/api.ts`)

Replace the stub `AgentRunOut` interface and stub `fetchAgentRuns`/`startAgentRun` functions with fully typed implementations matching `AgentRunOut` schema above.

---

## Files To Modify

| File | Change |
|---|---|
| `packages/workflows/forge_workflows/graph.py` | Remove inline imports + DB access from all 10 nodes; accept `llm`, `embedder`, `vector_store` in `build_graph()` |
| `packages/workflows/forge_workflows/state.py` | Add `raw_issues`, `collection_name`, `agent_run_id` fields to `SentinelState` |
| `apps/api/app/main.py` | Register `agent_runs_router` |
| `apps/web/src/lib/api.ts` | Replace stub `AgentRunOut` interface + agent fetch functions |
| `apps/web/src/app/agents/page.tsx` | Replace stub with real component |
| `apps/web/src/app/agents/[runId]/page.tsx` | Replace stub with real component |

---

## Files To Create

### Backend

```
apps/api/app/models/agent_run.py
apps/api/app/repositories/agent_run_repo.py
apps/api/app/schemas/agent_run.py
apps/api/app/services/brain_service.py
apps/api/app/api/agent_runs.py
alembic/versions/<timestamp>_add_agent_runs_table.py
```

### Frontend

```
apps/web/src/components/agents/agents-page.tsx
apps/web/src/components/agents/agent-run-detail.tsx
apps/web/src/components/agents/start-agent-run-button.tsx
```

---

## New Packages

No new Python packages.

No new npm packages.

`langchain-google-genai` is already installed (used in `graph.py`). `langgraph` already installed. No approvals needed.

---

## Implementation Rules

- TypeScript strict mode throughout.
- `SentinelState` fields are typed Pydantic models — no raw `dict` passed between nodes.
- `BrainService` is the only place that reads from `app.database` before graph invocation — graph nodes must not import `app.*` directly.
- `build_graph(llm, embedder, vector_store)` receives constructed instances — no lazy construction inside nodes.
- `AgentRun.result` is stored as JSONB using `.model_dump()` on the final state — no raw dicts in application code.
- Background task updates `AgentRun.status` and `AgentRun.current_node` after each node completes via a LangGraph streaming callback or a post-run update.
- No business logic inside API route handlers — `agent_runs.py` calls `brain_service` only.
- `agent_run_repo.py` follows the same pattern as `ingestion_repo.py`.
- Docker sandbox execution is not required for this feature (code is not executed, only generated as patches).

---

## Definition Of Done

- [ ] `POST /api/agent-runs` accepts `repository_id` + optional `target_issue_id`, returns `run_id`
- [ ] `GET /api/agent-runs/{run_id}` returns correct `status` that updates as the pipeline progresses
- [ ] `graph.py` contains zero `from app.` imports and zero inline `import` statements inside node functions
- [ ] `build_graph(llm, embedder, vector_store)` signature verified: no LLM construction inside nodes
- [ ] `SentinelState` has `raw_issues`, `collection_name`, `agent_run_id` fields
- [ ] `AgentRun` DB record created with `pending` status before background task starts
- [ ] `AgentRun.status` transitions to `running` → final `completed` or `failed`
- [ ] `AgentRun.result` JSONB contains `pull_request_draft`, `plan`, `review` when completed
- [ ] Alembic migration runs cleanly: `alembic upgrade head`
- [ ] `/agents` page lists runs (empty state when none exist)
- [ ] `/agents/:runId` page renders run detail without runtime errors
- [ ] `tsc --noEmit` passes with no errors
- [ ] `ruff check apps/api packages/` passes with no new violations

---

## Architecture Impact

**Affected systems:** `packages/workflows` (graph decoupled from app layer), `apps/api` (new model + service + router), `apps/web` (agents pages become real).

**Dependencies introduced:**
- `apps/api` → `packages/workflows` (already exists via editable install)
- `apps/api` → `packages/agents` (already exists)
- `BrainService` is the single integration point — it owns the boundary between app infrastructure and package logic

**Scalability concerns:** Each `AgentRun` fires an async background task in the same FastAPI process. For MVP this is acceptable. Future: move to a task queue (Celery/ARQ) with a dedicated worker process. The `AgentRun` model is queue-agnostic by design.

**Future extensions:**
- Real-time status streaming via SSE or WebSocket (`GET /api/agent-runs/{run_id}/stream`)
- Agent run retry endpoint (`POST /api/agent-runs/{run_id}/retry`)
- Per-node state snapshots stored in a `agent_run_events` table for the Execution Timeline page

---

## Risks

| Risk | Mitigation |
|---|---|
| LangGraph streaming API changes between versions | Wrap `graph.astream()` in `BrainService`; isolate version coupling to one file |
| Inline DB queries in `graph.py` currently pass tests that use `app.database` | Tests must be updated to use the new `BrainService` entry point; mock at the service boundary, not inside nodes |
| `SentinelState` JSONB serialization of nested Pydantic models | Use `.model_dump(mode="json")` for all Pydantic → JSONB serialization; validated at `AgentRunResult` deserialization time |
| Long-running pipeline (5–10+ LLM calls) blocks FastAPI event loop | All agent calls are `await`; `asyncio.create_task` used for background execution — same pattern as `ingestion_service` |
| Google Generative AI rate limits during multi-node pipeline | `settings.brain_llm_model` is configurable; retry logic already exists in each agent's fallback path |