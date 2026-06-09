# Spec: Implementing File Structure & Proper Routing

## Overview

This feature establishes the complete, canonical file structure for both the `apps/web` Next.js frontend and the `apps/api` FastAPI backend, and wires up all routing (page routes + API routes) that the MVP requires.

Currently the project has only two active web routes (`/` and `/repositories/[id]`) and a single API router group (`/api/repositories`). The remaining pages listed in `CLAUDE.md` — Issues Explorer, Agent Center, Planning Board, Execution Timeline, Pull Request Center — are entirely absent. On the API side, there are no routers for issues, agents, workflows, or pull requests.

This spec locks in the full directory tree, naming conventions, and import boundaries so every subsequent feature (Agents, Workflows, PRs) has a stable skeleton to build into without reorganising existing code.

---

## Depends On

- `01-generate-skeleton` — monorepo scaffolding, tooling, shared packages
- `02-repository-ingestion` — repository model, ingestion pipeline, `/api/repositories` router (already implemented)

---

## User Story

As a developer implementing Forge agents and workflows, I want a complete, consistent file structure with all routes stubbed out so I can add real functionality to named files in known locations without creating directory structure conflicts or routing ambiguities.

As a user opening the Forge dashboard, I want to navigate to Issues, Agents, Planning, Timeline, and Pull Requests pages (even if they show "coming soon" stubs) so the app feels navigable and purposeful from day one.

---

## Agent Changes

No new agents created. No existing agents modified.

The `packages/agents/` directory already contains all six primary agents as stubs; this feature does not touch them.

---

## Workflow Changes

No LangGraph modifications. This feature is purely structural.

---

## Database Changes

No new tables. No schema modifications.

---

## Retrieval Changes

No vector database changes.

---

## API Changes

### New Routers (stub implementations — 200 OK with empty/placeholder response)

All routers are registered under `/api` prefix in `apps/api/app/main.py`.

---

#### Issues Router

**File:** `apps/api/app/api/issues.py`

```
GET /api/issues
```

Request query params:
```
repository_id: str | None
state: "open" | "closed" | "all"  (default: "open")
limit: int  (default: 20)
offset: int  (default: 0)
```

Response:
```json
{
  "total": 0,
  "issues": []
}
```

```
GET /api/issues/{issue_id}
```

Response: `IssueOut` schema (reuse existing issue model from `app/models/issue.py`)

```
POST /api/issues/{issue_id}/analyze
```

Request: `{}`  
Response:
```json
{
  "issue_id": "<uuid>",
  "status": "queued"
}
```

---

#### Agents Router

**File:** `apps/api/app/api/agents.py`

```
GET /api/agents/runs
```

Response:
```json
{
  "total": 0,
  "runs": []
}
```

```
GET /api/agents/runs/{run_id}
```

Response: `AgentRunOut` schema (define below)

```
POST /api/agents/runs
```

Request:
```json
{
  "repository_id": "string",
  "issue_id": "string"
}
```
Response:
```json
{
  "run_id": "string",
  "status": "queued"
}
```

---

#### Workflows Router

**File:** `apps/api/app/api/workflows.py`

```
GET /api/workflows/{run_id}/state
```

Response:
```json
{
  "run_id": "string",
  "current_node": "string | null",
  "nodes_completed": [],
  "nodes_pending": [],
  "status": "pending | running | completed | failed"
}
```

---

#### Pull Requests Router

**File:** `apps/api/app/api/pull_requests.py`

```
GET /api/pull-requests
```

Query params: `repository_id: str | None`

Response:
```json
{
  "total": 0,
  "pull_requests": []
}
```

```
GET /api/pull-requests/{pr_id}
```

Response: `PullRequestOut` schema (define below)

---

### New Pydantic Schemas

**File:** `apps/api/app/schemas/agent.py`

```python
class AgentRunOut(BaseModel):
    id: str
    repository_id: str
    issue_id: str
    status: str          # queued | running | completed | failed
    current_node: str | None
    created_at: datetime
    completed_at: datetime | None
```

**File:** `apps/api/app/schemas/pull_request.py`

```python
class PullRequestOut(BaseModel):
    id: str
    repository_id: str
    issue_id: str | None
    title: str
    description: str | None
    github_url: str | None
    status: str          # draft | open | merged | closed
    created_at: datetime
```

**File:** `apps/api/app/schemas/workflow.py`

```python
class WorkflowStateOut(BaseModel):
    run_id: str
    current_node: str | None
    nodes_completed: list[str]
    nodes_pending: list[str]
    status: str
```

---

## Frontend Changes

### Pages to Create

All pages are Server Components unless noted. Stub pages return a minimal layout with a section heading and a "Coming soon" notice — no placeholder lorem ipsum, no fake data.

| Route | File | Description |
|---|---|---|
| `/` | `apps/web/src/app/page.tsx` | Dashboard — already exists, no change |
| `/repositories` | `apps/web/src/app/repositories/page.tsx` | Already exists, no change |
| `/repositories/[id]` | `apps/web/src/app/repositories/[id]/page.tsx` | Already exists, no change |
| `/issues` | `apps/web/src/app/issues/page.tsx` | Issue Explorer — global list across repos |
| `/issues/[id]` | `apps/web/src/app/issues/[id]/page.tsx` | Single issue detail + analysis trigger |
| `/agents` | `apps/web/src/app/agents/page.tsx` | Agent Center — list of agent runs |
| `/agents/[runId]` | `apps/web/src/app/agents/[runId]/page.tsx` | Single agent run detail + live timeline |
| `/planning` | `apps/web/src/app/planning/page.tsx` | Planning Board — plan viewer |
| `/planning/[runId]` | `apps/web/src/app/planning/[runId]/page.tsx` | Single plan detail |
| `/timeline` | `apps/web/src/app/timeline/page.tsx` | Execution Timeline — global execution history |
| `/pull-requests` | `apps/web/src/app/pull-requests/page.tsx` | Pull Request Center |
| `/pull-requests/[id]` | `apps/web/src/app/pull-requests/[id]/page.tsx` | Single PR detail |

### Components to Create

**Shared layout components** (all in `apps/web/src/components/`):

```
apps/web/src/components/
├── layout/
│   ├── page-header.tsx       # <h2> + optional subtitle, consistent heading component
│   └── empty-state.tsx       # "No X yet" empty state with optional CTA
```

**Per-section stub components:**

```
apps/web/src/components/
├── issues/
│   ├── issues-page.tsx           # server component — issues list page body
│   └── issue-detail.tsx          # server component — single issue body (stub)
├── agents/
│   ├── agents-page.tsx           # server component — agent runs list (stub)
│   └── agent-run-detail.tsx      # server component — single run detail (stub)
├── planning/
│   ├── planning-page.tsx         # server component — planning board (stub)
│   └── plan-detail.tsx           # server component — plan detail (stub)
├── timeline/
│   └── timeline-page.tsx         # server component — execution timeline (stub)
└── pull-requests/
    ├── pull-requests-page.tsx    # server component — PR list (stub)
    └── pull-request-detail.tsx   # server component — single PR detail (stub)
```

### Navigation Update

`apps/web/src/components/app-shell.tsx` — update `navItems` array to include all routes:

```ts
const navItems = [
  { label: "Dashboard",      href: "/" },
  { label: "Repositories",   href: "/repositories" },
  { label: "Issues",         href: "/issues" },
  { label: "Agents",         href: "/agents" },
  { label: "Planning",       href: "/planning" },
  { label: "Timeline",       href: "/timeline" },
  { label: "Pull Requests",  href: "/pull-requests" },
]
```

### API Client Extensions

`apps/web/src/lib/api.ts` — add typed fetch functions for all new routers:

```ts
// Issues
fetchIssuesGlobal(params?)          // GET /issues
fetchIssue(issueId)                 // GET /issues/:id
triggerIssueAnalysis(issueId)       // POST /issues/:id/analyze

// Agents
fetchAgentRuns(params?)             // GET /agents/runs
fetchAgentRun(runId)               // GET /agents/runs/:id
startAgentRun(body)                // POST /agents/runs

// Workflows
fetchWorkflowState(runId)          // GET /workflows/:runId/state

// Pull Requests
fetchPullRequests(params?)          // GET /pull-requests
fetchPullRequest(prId)             // GET /pull-requests/:id
```

Add corresponding TypeScript interfaces:

```ts
interface AgentRunOut { ... }
interface WorkflowStateOut { ... }
interface PullRequestOut { ... }
```

---

## Files To Modify

| File | Change |
|---|---|
| `apps/api/app/main.py` | Register 4 new routers |
| `apps/web/src/components/app-shell.tsx` | Expand `navItems` |
| `apps/web/src/lib/api.ts` | Add new fetch functions + interfaces |
| `apps/web/src/app/repositories/page.tsx` | No change — kept for reference |

---

## Files To Create

### Backend

```
apps/api/app/api/issues.py
apps/api/app/api/agents.py
apps/api/app/api/workflows.py
apps/api/app/api/pull_requests.py
apps/api/app/schemas/agent.py
apps/api/app/schemas/pull_request.py
apps/api/app/schemas/workflow.py
```

### Frontend

```
apps/web/src/app/issues/page.tsx
apps/web/src/app/issues/[id]/page.tsx
apps/web/src/app/agents/page.tsx
apps/web/src/app/agents/[runId]/page.tsx
apps/web/src/app/planning/page.tsx
apps/web/src/app/planning/[runId]/page.tsx
apps/web/src/app/timeline/page.tsx
apps/web/src/app/pull-requests/page.tsx
apps/web/src/app/pull-requests/[id]/page.tsx
apps/web/src/components/layout/page-header.tsx
apps/web/src/components/layout/empty-state.tsx
apps/web/src/components/issues/issues-page.tsx
apps/web/src/components/issues/issue-detail.tsx
apps/web/src/components/agents/agents-page.tsx
apps/web/src/components/agents/agent-run-detail.tsx
apps/web/src/components/planning/planning-page.tsx
apps/web/src/components/planning/plan-detail.tsx
apps/web/src/components/timeline/timeline-page.tsx
apps/web/src/components/pull-requests/pull-requests-page.tsx
apps/web/src/components/pull-requests/pull-request-detail.tsx
```

---

## New Packages

No new packages required.

---

## Implementation Rules

- TypeScript strict mode throughout (`noImplicitAny`, no untyped `fetch` casts).
- All new API schemas use Pydantic `BaseModel`; no raw dicts.
- New FastAPI routers follow the same pattern as `app/api/repositories.py`: `APIRouter` with `prefix` and `tags`, imported in `main.py`.
- Stub API endpoints return HTTP 200 with valid empty-collection or placeholder responses — no `NotImplementedError`, no `HTTPException(501)`.
- Stub frontend pages must render without errors when the API is unreachable (wrap `fetch` in try/catch, show `EmptyState`).
- No business logic inside route handlers — service layer calls only (even if the service just returns an empty list for now).
- `PageHeader` and `EmptyState` components must be reusable across all section pages.
- Do not add `"use client"` to stub pages — they are Server Components.
- No mock data / hardcoded fake lists.

---

## Definition Of Done

- [ ] All 4 new API routers registered in `main.py` and reachable (`curl /api/issues`, `/api/agents/runs`, `/api/workflows/x/state`, `/api/pull-requests`)
- [ ] All 3 new Pydantic schema files pass `mypy --strict` (or `ruff check`)
- [ ] All 9 new Next.js page routes render without runtime errors (200 OK in browser)
- [ ] Navigation sidebar shows all 7 items and links resolve correctly
- [ ] `apps/web/src/lib/api.ts` exports typed functions for all new endpoints
- [ ] No TypeScript errors (`tsc --noEmit` passes)
- [ ] Stub pages display `EmptyState` component when API data is absent
- [ ] `PageHeader` component used consistently on all new pages
- [ ] No new `eslint` warnings introduced

---

## Architecture Impact

**Affected systems:** `apps/web` routing tree, `apps/api` router registry, shared TypeScript API client.

**Dependencies introduced:** None — this feature only introduces structural scaffolding.

**Scalability concerns:** None specific to this feature; stub routes add negligible overhead.

**Future extensions:** Every subsequent agent/workflow/PR feature will land directly into the stub files created here (e.g., `agents-page.tsx` becomes real when the agent run model is implemented). This avoids structural churn in future PRs.

---

## Risks

| Risk | Mitigation |
|---|---|
| Next.js dynamic segment naming conflicts (e.g., `[id]` vs `[runId]`) | Use consistent `[id]` for resource-level routes; only use named slugs (`[runId]`) where the same page tree has both a parent `[id]` and a child dynamic segment |
| Stub API routers imported before models exist | Define schemas inline in schema files with no DB dependency; service stubs return empty lists without DB queries |
| TypeScript interface drift between frontend `api.ts` and backend Pydantic schemas | Schemas are the source of truth; frontend interfaces are manually kept in sync until an OpenAPI codegen step is introduced in a future feature |
| Accidental `"use client"` pollution causing hydration issues | Lint rule + code review gate; all new pages start as Server Components |
