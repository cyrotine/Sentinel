# Spec: Real-Time Frontend Synchronization

## Overview

The frontend has two broken synchronization contracts with the backend:

1. **Agent run pipeline stages show a stale previous stage** while the agent is actively executing a later one. The pipeline visualization derives its active stage from whether result objects exist in `result.*` fields — but result fields are only written after a node *completes*. So when the backend is mid-execution of `reviewer`, `result.review` is still null and the UI displays the previous completed stage. The backend already writes `current_node` to the database on every node transition; the frontend simply ignores it for pipeline display purposes.

2. **Repository cards on the list page never refresh** during ingestion. `/repositories/page.tsx` is a server component that renders once. After that render, ingestion status is frozen at whatever value existed at page load. Users see "cloning" or "embedding" until they manually navigate away and back.

Both issues are purely frontend bugs. The backend contract is already correct:
- `AgentRunOut.current_node` is written at node start (`brain_service.py:150`)
- `IngestionRunOut.status` is updated continuously during ingestion

This spec fixes both.

---

## Depends On

- Phase 7 (Auto Repair Loop) — already complete. `current_node`, `iteration`, and `repair_context` fields are already present in the schema and populated by the backend.
- The sentinel-brain feature branch, which introduced the current UI design (pipeline steps, activity feed, diff viewer).

---

## User Story

As an engineer watching Forge process an issue, I want the pipeline visualization to advance in real time — showing "Review" as the active step while the reviewer agent is running, not after it finishes — so I can follow the autonomous workflow as it happens rather than seeing a sudden jump from "Issue Selected" to "Completed."

As an engineer who just connected a repository, I want the repository card on the list page to update its ingestion badge from "cloning" → "analyzing" → "embedding" → "completed" without needing to reload the page.

---

## Agent Changes

No agent changes.

---

## Workflow Changes

No workflow changes.

---

## Database Changes

No database changes.

---

## Retrieval Changes

No retrieval changes.

---

## API Changes

No new endpoints. Existing polling endpoints are sufficient:
- `GET /api/agent-runs/{run_id}` — returns `current_node` already
- `GET /api/repositories` — returns `latest_ingestion.status` already

---

## Frontend Changes

### Root Cause 1 — Pipeline `activeStage` uses result-presence, not `current_node`

**File**: `apps/web/src/components/agents/agent-run-detail.tsx`, lines 178–185

Current logic:
```tsx
const activeStage = 
  isFailed ? "failed" :
  isPrDone ? "completed" :
  isReviewDone ? "reviewer" :      // only true AFTER review result is written
  isDevDone ? "validator" :
  isPlanDone ? "developer" :
  isIssueDone ? "planner" : 
  "issue_selection"
```

This derives `activeStage` from result fields. But result fields are written only when a node *finishes*, so the active stage always lags one node behind.

The backend already writes `run.current_node` at node *start* (e.g., `"reviewer"` is written when the reviewer node begins, before `result.review` exists). This is the correct source of truth.

**Fix**: Map `run.current_node` directly to a pipeline stage constant. Fall back to result-based inference only when `current_node` is null (pending or completed).

LangGraph node → pipeline stage mapping (from `graph.py` constants):

| `current_node` value | Pipeline stage |
|---|---|
| `repo_analyzer` | `issue_selection` |
| `issue_analyzer` | `issue_selection` |
| `retrieve_context` | `issue_selection` |
| `load_full_files` | `issue_selection` |
| `planner` | `planner` |
| `developer` | `developer` |
| `apply_patches` | `developer` |
| `validator` | `developer` |
| `test_agent` | `developer` |
| `reviewer` | `reviewer` |
| `pr_generator` | `pull_request` |

The `isXDone` booleans (result-presence checks) remain correct for marking *completed* steps (filled blue circle). Only the `activeStage` derivation changes.

**Activity feed** (lines 264–274): currently shows `run.current_node` as a generic "running node" label at the bottom. No structural changes needed — the feed already updates with each poll since it renders from live `run` state.

---

### Root Cause 2 — Repositories list page renders once (server component, no polling)

**File**: `apps/web/src/app/repositories/page.tsx`

Current: server component, fetches `fetchRepositories()` once at render time, passes static data to `RepositoryCard` children. No mechanism to update after the initial render.

**Fix**: Extract the grid of `RepositoryCard`s into a new client component `RepositoriesListClient` that:
- Accepts `initialRepos: RepositoryOut[]` from the server page (avoids loading flash)
- Polls `fetchRepositories()` every **3 seconds** while any repository has a non-terminal ingestion status (`status` not in `["completed", "failed"]` and `latest_ingestion !== null`)
- Stops polling once all ingestions are terminal
- Passes updated `RepositoryOut` to `RepositoryCard` on each successful poll
- Silently swallows fetch errors (same pattern as `IngestionProgress`)

The server page (`repositories/page.tsx`) stays a server component and simply passes initial data to `RepositoriesListClient`. The `RepositoryCard` itself requires no changes — it already renders whatever `repo` prop it receives.

---

### Pages

No new pages.

### Components

**Modify**: `apps/web/src/components/agents/agent-run-detail.tsx`
- Replace result-presence `activeStage` derivation with `current_node`-based mapping
- Add `NODE_TO_STAGE` map constant at top of file

**Create**: `apps/web/src/components/repositories/repositories-list-client.tsx`
- Client component with polling loop
- Renders `RepositoryCard` grid from polled state
- Accepts `initialRepos: RepositoryOut[]`
- Stops polling when all terminal

**Modify**: `apps/web/src/app/repositories/page.tsx`
- Import and render `RepositoriesListClient` instead of inline `RepositoryCard` grid
- Pass `repos` as `initialRepos` prop

### State management

No new state management libraries. Uses existing `useState`/`useEffect` pattern already established in `IngestionProgress` and `AgentRunDetail`.

---

## Files To Modify

| File | Change |
|---|---|
| `apps/web/src/components/agents/agent-run-detail.tsx` | Add `NODE_TO_STAGE` map; replace `activeStage` derivation to use `run.current_node` |
| `apps/web/src/app/repositories/page.tsx` | Replace inline card grid with `<RepositoriesListClient initialRepos={repos} />` |

## Files To Create

| File | Purpose |
|---|---|
| `apps/web/src/components/repositories/repositories-list-client.tsx` | Client polling wrapper for repository card grid |

---

## New Packages

No new packages.

---

## Implementation Rules

- TypeScript strict mode throughout
- No `any` without justification
- Polling must stop on component unmount (clear `setTimeout`/`setInterval` in cleanup)
- Polling must stop when all statuses are terminal (avoid infinite background fetches on completed repos)
- No business logic in route handlers
- `RepositoryCard` stays a pure presentational component — it must not be converted to a client component
- `NODE_TO_STAGE` must be typed as `Record<string, PipelineStage>` where `PipelineStage` is a union type, not a free string

---

## Definition Of Done

- [ ] During a running agent run, the pipeline step for the *current* executing node shows a spinning loader and glowing border — not the previously completed node
- [ ] When `current_node` transitions from `"developer"` to `"reviewer"`, the Review step becomes active within one poll cycle (≤ 2 seconds)
- [ ] When `current_node` is null and `status` is "completed", all five pipeline steps show as completed (filled blue)
- [ ] When `current_node` is null and `status` is "pending"/"running" with no result data, the first step (Issue Selected) shows as active
- [ ] Repository list page: a repository with `ingestion.status === "cloning"` updates its badge to "completed" within 3 seconds of ingestion completing — without a page reload
- [ ] Repository list page: once all repositories show terminal ingestion status, polling stops (verify via browser devtools Network tab — no more requests to `/repositories`)
- [ ] Polling stops on unmount: navigating away from `/repositories` stops the polling interval
- [ ] No regressions: completed runs still display all pipeline steps as filled/blue
- [ ] No regressions: failed runs still show red indicators on the appropriate step
- [ ] TypeScript compiles with zero errors on `apps/web`

---

## Architecture Impact

**Affected systems**: Frontend only — two components, one new component, one page wrapper change.

**Dependencies introduced**: None.

**Scalability concerns**: The `RepositoriesListClient` polls `GET /repositories` which returns all repos. If a user has hundreds of repositories, this call could grow. For the current MVP scope (1–5 repos), this is not a concern. A future optimization would be to poll only repos with non-terminal ingestion status individually.

**Future extensions**:
- Replace REST polling with Server-Sent Events (`EventSource`) on a `GET /api/agent-runs/{id}/stream` endpoint for sub-second latency. The `NODE_TO_STAGE` map introduced here will be reused directly — only the data transport layer changes.
- The same client-polling pattern from `RepositoriesListClient` could be extracted into a generic `usePolling(fetchFn, interval, shouldStop)` hook shared across the app.

---

## Risks

| Risk | Mitigation |
|---|---|
| `current_node` string values change if LangGraph graph node names are renamed | `NODE_TO_STAGE` map uses explicit string literals matching `graph.py` constants; a mismatch will cause the unknown node to fall through to result-based inference (graceful degradation, not a crash) |
| Backend returns `current_node` that isn't in `NODE_TO_STAGE` (e.g., during repair loop new nodes) | Fall through to result-based `activeStage` inference — existing behavior, not a regression |
| `fetchRepositories` 3s polling adds load when no ingestion is running | Polling stops when all `latest_ingestion` statuses are terminal — no idle polling |
| Race condition: poll returns stale data after completion | Both polling loops check terminal status on every response and clear the interval when reached |