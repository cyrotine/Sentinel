# Spec: Specified Issue Tackler

## Overview

This feature allows users to select a specific GitHub issue and trigger the full Forge agent pipeline exclusively on that issue. Currently the pipeline fetches all open issues, runs LLM classification across every one, and lets `IssuePrioritizerAgent` autonomously choose which to tackle. This is appropriate for fully hands-off mode, but removes user agency.

With this feature the user can point at a single issue from the repository detail page (or from the agents page) and instruct Forge to tackle exactly that issue. The pipeline short-circuits the full-issue-classification sweep and analyzes only the targeted issue, making the run faster and the selection transparent.

Why it exists: autonomous selection is powerful but opaque. Users need a direct, deterministic path to say "fix *this*" without fighting an LLM ranking they cannot control.

How it contributes to autonomous software engineering: it preserves all six agents — repo analysis, planning, development, testing, review, PR generation — while giving humans a precise entry point. The "Think → Decide → Act" loop is unchanged; only the "Decide" phase becomes user-directed.

---

## Depends On

- 01: Generate Skeleton
- 02: Repository Ingestion
- 04: Simplify Code Structure / Incorporate Packages Logic

---

## User Story

As a repository owner, I want to select a specific open issue from my repository and click "Tackle this issue" so that Forge runs its full agent pipeline against exactly that issue, giving me predictable, issue-targeted output rather than waiting for the LLM to choose one autonomously.

---

## Agent Changes

### Create

No new agents.

### Delete

**`IssuePrioritizerAgent`** (`packages/agents/forge_agents/issue_prioritizer.py`):

Remove entirely. Its only job was to rank classified issues and pick one. With user-driven issue selection, there is nothing to rank — exactly one issue is always analyzed, and the result is promoted to `selected_issue` directly inside the `issue_analyzer` node. Keeping it would burn tokens on a no-op LLM call against a single-item list.

Remove its import from `packages/workflows/forge_workflows/graph.py` and `packages/agents/forge_agents/__init__.py`.

### Modify

**`issue_analyzer` graph node** (`packages/workflows/forge_workflows/graph.py`):

Extend the node to do two things instead of one:

1. **Filter**: slice `state.inputs.raw_issues` to the single entry where `issue["issue_id"] == state.target_issue_id` before calling `IssueAnalyzerAgent.analyze()`. Raise a descriptive `ValueError` if `target_issue_id` is missing or not found in `raw_issues` — the run should fail fast rather than silently analyzing every issue.

2. **Promote**: after analysis, construct a `SelectedIssue` directly from `issue_analyses[0]` and include it in the return dict. No separate prioritizer node is needed.

```python
# Pseudo-code for the new node body
issues_to_analyze = [i for i in state.inputs.raw_issues if i["issue_id"] == state.target_issue_id]
if not issues_to_analyze:
    raise ValueError(f"target_issue_id {state.target_issue_id!r} not found in raw_issues")

analyses = await IssueAnalyzerAgent(llm).analyze(issues=issues_to_analyze, repo_context=state.repo_context)
analysis = analyses[0]

selected = SelectedIssue(
    issue_id=analysis.issue_id,
    number=analysis.number,
    title=analysis.title,
    body=analysis.body,
    reasoning=f"User-selected issue #{analysis.number}: {analysis.issue_type}/{analysis.severity}.",
    estimated_complexity=_estimate_complexity(analysis),
)
return {"issue_analyses": analyses, "selected_issue": selected, ...}
```

`_estimate_complexity` can be lifted verbatim from `IssuePrioritizerAgent._estimate_complexity_from_analysis` as a module-level helper in `graph.py` — no need for a separate agent class.

---

## Workflow Changes

### Inputs

`SentinelState.target_issue_id: str | None` — already exists. After this feature it is **effectively required**: the graph will raise `ValueError` at the `issue_analyzer` node if it is absent. No schema change; the field stays optional at the type level to avoid a breaking Pydantic migration, but the application layer (`AgentRunCreate`) enforces its presence.

### Outputs

No new state fields. `selected_issue` is now set by `issue_analyzer` rather than `issue_prioritizer` — same field, different producer.

### State Changes

No schema changes to `SentinelState` or `BrainInputs`.

### Graph Nodes

**Modified:** `issue_analyzer` — gains the filter + promote logic described in Agent Changes.

**Removed:** `issue_prioritizer` — node registration deleted from `graph.py`, constant `ISSUE_PRIORITIZER` removed.

### Graph Edges

Remove: `ISSUE_ANALYZER → ISSUE_PRIORITIZER` and `ISSUE_PRIORITIZER → RETRIEVE_CONTEXT`

Add: `ISSUE_ANALYZER → RETRIEVE_CONTEXT`

New linear path: `repo_analyzer → issue_analyzer → retrieve_context → planner → developer → …`

---

## Database Changes

No database changes. `agent_runs.target_issue_id` (nullable UUID) already exists and is populated correctly by `agent_run_repo.create`.

---

## Retrieval Changes

No retrieval changes. The vector search in `retrieve_context` already uses `selected_issue` title/body — no change needed.

---

## API Changes

No new endpoints. One existing schema tightened:

**`POST /api/agent-runs`** — `AgentRunCreate.target_issue_id` changes from `uuid.UUID | None = None` to `uuid.UUID`. The field becomes required. The API returns `422 Unprocessable Entity` if omitted.

```python
# Before
class AgentRunCreate(BaseModel):
    repository_id: uuid.UUID
    target_issue_id: uuid.UUID | None = None

# After
class AgentRunCreate(BaseModel):
    repository_id: uuid.UUID
    target_issue_id: uuid.UUID
```

Existing endpoints unchanged:
- `GET /api/repositories/{id}/issues` — returns `IssueListOut` with `IssueOut.id` (UUID string); frontend passes this as `target_issue_id`
- `GET /api/agent-runs/{run_id}` — `AgentRunOut.target_issue_id` stays `uuid.UUID | None` (historical runs may have null)

---

## Frontend Changes

### Pages

No new pages.

### Components

**Modified: `apps/web/src/components/repositories/issues-list.tsx`**
- Add props: `repositoryId: string`, `onTackle?: (issueId: string, issueTitle: string) => void`
- When `onTackle` is provided, render a "Tackle" button on each issue row
- Button shows a per-issue loading spinner while the run is being created (local `tacklingId` state)
- Disabled state prevents double-clicks
- On success: caller navigates; on error: show inline error text on the row

**Modified: `apps/web/src/components/repositories/repository-detail-client.tsx`**
- Import `startAgentRun` from `@/lib/api` and `useRouter`
- Pass `repositoryId` and an `onTackle` handler to `IssuesList`
- Handler: calls `startAgentRun({ repository_id: repositoryId, target_issue_id: issueId })` → navigates to `/agents/${run_id}`

**Modified: `apps/web/src/components/agents/start-agent-run-button.tsx`**
- Convert the single-step "pick repo → Run agents" flow into a two-step flow:
  - Step 1: Repository selector (existing)
  - Step 2: Issue picker — fetches `GET /repositories/{id}/issues` for the selected repo, renders a scrollable list with radio-select rows
- An issue **must** be selected before the "Run agents" button is enabled — no "Let agents choose" option, since `target_issue_id` is now required
- Pass `target_issue_id` to `startAgentRun`; button remains disabled until both repo and issue are selected

**Modified: `apps/web/src/components/agents/agent-run-detail.tsx`**
- In the result section, show the selected issue card prominently:
  - Issue number + title
  - Badge: "User-selected" when `run.target_issue_id` is non-null, "Auto-selected" otherwise
  - `estimated_complexity` chip and `reasoning` text (already in `SelectedIssueShape`)

### Visualizations

No new visualizations.

### Dashboard Modules

No dashboard changes.

### State Management

Local `useState` only. No global state library introduced.

---

## Files To Modify

```
packages/workflows/forge_workflows/graph.py
packages/agents/forge_agents/__init__.py
apps/api/app/schemas/agent_run.py
apps/web/src/components/repositories/issues-list.tsx
apps/web/src/components/repositories/repository-detail-client.tsx
apps/web/src/components/agents/start-agent-run-button.tsx
apps/web/src/components/agents/agent-run-detail.tsx
apps/web/src/lib/api.ts
```

---

## Files To Delete

```
packages/agents/forge_agents/issue_prioritizer.py
```

---

## Files To Create

None.

---

## New Packages

No new packages.

---

## Implementation Rules

- TypeScript strict mode throughout; no `any` without justification
- All LangGraph state remains typed via Pydantic — no raw dict passing
- No business logic in API route handlers
- Repository/service pattern preserved on the backend
- The graph node modification must be a targeted edit — no refactor of surrounding logic
- The frontend `onTackle` callback pattern avoids prop-drilling beyond one level; do not lift further
- The two-step agent start flow must degrade gracefully: if the issue fetch fails, show an inline error — no fallback to auto-selection (the prioritizer is gone)
- `_estimate_complexity_from_analysis` lifted from deleted `IssuePrioritizerAgent` into `graph.py` as a module-level private function — do not duplicate logic

---

## Definition Of Done

- [ ] `packages/agents/forge_agents/issue_prioritizer.py` is deleted; its import removed from `__init__.py`
- [ ] `IssuePrioritizerAgent` import and `ISSUE_PRIORITIZER` constant removed from `graph.py`
- [ ] `issue_prioritizer` node no longer registered in the `StateGraph`
- [ ] Edge `ISSUE_ANALYZER → RETRIEVE_CONTEXT` wired; `ISSUE_ANALYZER → ISSUE_PRIORITIZER` edge does not exist
- [ ] `issue_analyzer` node filters `raw_issues` to target issue only and raises `ValueError` if `target_issue_id` is absent or not found
- [ ] `issue_analyzer` node returns `selected_issue` in its dict, populated from the single `IssueAnalysis`
- [ ] `_estimate_complexity_from_analysis` helper present in `graph.py` (lifted from deleted file)
- [ ] `AgentRunCreate.target_issue_id` is a required `uuid.UUID` (no default, no `None`)
- [ ] `POST /api/agent-runs` returns `422` when `target_issue_id` is omitted
- [ ] `startAgentRun` in `apps/web/src/lib/api.ts` has `target_issue_id: string` as a required field
- [ ] Repository detail page: each issue row has a "Tackle" button
- [ ] Clicking "Tackle" creates an `AgentRun` with `target_issue_id` and navigates to `/agents/{run_id}`
- [ ] Per-issue loading state prevents double-submission
- [ ] Agents page: step 2 shows issues for selected repo; "Run agents" disabled until an issue is chosen
- [ ] No "Let agents choose" option exists anywhere in the UI
- [ ] `AgentRunDetail` shows "User-selected" badge (all runs now have a target, badge always shows)
- [ ] Selected issue number and title displayed in the run detail panel
- [ ] Full end-to-end run reaches `completed` with `selected_issue.number` matching the targeted issue

---

## Architecture Impact

**Affected systems:**
- LangGraph pipeline — `issue_analyzer` node extended; `issue_prioritizer` node removed; one edge removed, one added
- `packages/agents/forge_agents/issue_prioritizer.py` — deleted
- `apps/api/app/schemas/agent_run.py` — `target_issue_id` made required
- Frontend repository detail page — adds actionable "Tackle" trigger per issue
- Frontend agents page — adds mandatory issue selection step to run creation

**Dependencies introduced:**
- None. The feature uses only existing API contracts, state fields, and agent interfaces.

**Scalability concerns:**
- Targeted analysis reduces LLM calls from N (all issues) to 1, improving latency and token usage for user-directed runs.
- The issues fetch in the agents page two-step flow adds one extra API call per repository selection; this is acceptable given the interactive context.

**Future extensions:**
- Bulk-select multiple issues for sequential or parallel runs
- Webhook-triggered runs where a GitHub label (e.g. `forge:tackle`) sets `target_issue_id` automatically
- Re-introduce an optional auto-select mode later as a separate, explicitly opt-in feature if needed

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| `target_issue_id` UUID format mismatch between frontend string and backend UUID | Low | Backend coerces via Pydantic `uuid.UUID`; frontend passes `IssueOut.id` which is already a valid UUID string |
| `raw_issues` filter uses `issue["issue_id"]` (Postgres UUID string) not `issue["number"]` (GitHub integer) | Medium | Explicitly document and test the comparison: `issue["issue_id"] == state.target_issue_id`; they are both string-form Postgres UUIDs |
| Issue fetch in agents start flow slow on repos with many issues | Low | `fetchIssues` supports `limit`; cap at 50 in the picker |
| LLM failure in single-issue analysis — no ranking fallback remains | Low | `IssueAnalyzerAgent._fallback_analysis` still runs; the `issue_analyzer` node promotes whatever analysis comes back (even the default fallback) to `selected_issue` |
| User selects an issue closed between page load and run start | Low | `issue_analyzer` raises `ValueError` (target not in `raw_issues`); run fails with a clear error message visible in the detail page |
| Existing agent runs in the database have `target_issue_id = NULL` | Low | `AgentRunOut.target_issue_id` stays `uuid.UUID | None`; only `AgentRunCreate` (new runs) enforces the non-null constraint |
