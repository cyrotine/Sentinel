# Spec: Live Agent Outputs

## Overview

While Forge processes an issue, the agent-run detail page (`agent-run-detail.tsx`)
shows almost nothing until the entire pipeline finishes. The hero title, the rich
output cards (Execution Plan, Code Review, Transparent Code Changes), and most of
the activity feed are all gated on `result.*` fields — and `result` is only written
to the database **once, at run completion** (`brain_service.py:176-183`). For the
30–90 seconds the run is executing, the user stares at a spinner and a single
"Initializing autonomous agent workspace..." line. The screenshot the user shared
is the *completed* state; the *running* state is effectively blank.

This is a wasted engagement opportunity. The backend already computes every
intermediate output and even holds it in memory:

- `BrainService` accumulates each node's partial output into `accumulator` and
  writes a serialized `snapshot` into `self._active_snapshots[run_id]` on **every**
  node transition (`brain_service.py:140-144`).
- `get_snapshot(run_id)` already exists (`brain_service.py:82-83`) but is **never
  exposed by any API endpoint**.
- `AgentRunOut.execution_snapshot: dict | None` already exists in the schema
  (`schemas/agent_run.py:43`) but is **never populated** — there is no
  `execution_snapshot` column on the `AgentRun` model, so `model_validate(run)`
  always leaves it `None`.

So the plumbing is 80% built and simply not connected. This feature connects it:
persist (or stream) the incremental snapshot so the polling frontend sees each
agent's output the instant it is produced, then enrich the UI so each output type
arrives as a distinct, animated card — issue analysis metadata, planner tasks +
affected files + dependencies, code diffs (already rendered), review findings
(comments, security issues, suggestions), validation/test results, and the PR draft
preview.

This contributes to autonomous software engineering by making the autonomy
**legible**: the user watches Forge *think → decide → act* in real time, which is
the core promise in CLAUDE.md ("Watch Forge analyze… plan… generate code… review
itself").

---

## Depends On

- **Spec 14 — Real-Time Frontend Synchronization** (current branch
  `feature/sentinel-brain`). Spec 14 fixed the *pipeline stage* indicator to track
  `current_node` live. This spec is the natural follow-up: it makes the *output
  content* (not just the stage dots) appear live. It reuses the same 2 s polling
  loop and the `NODE_TO_STAGE` mapping already in `agent-run-detail.tsx`.
- **Phase 7 — Auto Repair Loop** (complete). `iteration` and `repair_context` are
  already populated and surfaced; this spec extends that pattern to all outputs.

No new agents, no new workflow nodes, no new database tables.

---

## User Story

As an engineer who just kicked off an autonomous run, I want each agent's output to
appear on screen the moment that agent produces it — the issue analysis with its
severity and confidence, then the plan with its tasks and target files, then the
code diffs streaming in, then the reviewer's verdict — so that the run feels alive
and transparent instead of a 60-second spinner that suddenly snaps to "Completed."

---

## Agent Changes

### Create

No new agents.

### Modify

No agent changes. Every agent already returns the structured output this feature
displays (`IssueAnalysis`, `Plan`, `CodeChange`, `Review`, `ValidationResult`,
`TestResult`, `PullRequestDraft`). This is a transport + presentation feature.

---

## Workflow Changes

No LangGraph graph changes — no new nodes, no new edges, no state-shape changes.

The only behavioral change is in `BrainService.start()` (the application-layer
driver that streams the graph), which already iterates `graph.astream(...,
stream_mode="updates")`. The fix lives entirely in what it *persists* per chunk.

### Inputs

Unchanged.

### Outputs

Unchanged graph outputs. New: the per-node snapshot is now persisted to the
database (not just held in `_active_snapshots`).

### State Changes

None to `SentinelState`.

### Graph Nodes / Edges

Unchanged.

---

## Database Changes

### Modify

Table: `agent_runs`

The cleanest transport is to **persist the incremental snapshot into the existing
`result` JSONB column on every node transition**, instead of only at completion.
The `result` column already holds the exact same shape (`_RESULT_FIELDS`), so the
frontend needs no new field to read — it already reads `run.result.*`.

Decision (locked): **reuse `result`**, do not add an `execution_snapshot` column.
Reasoning:
- The frontend already renders entirely off `run.result.*`. Writing partial
  snapshots there means **zero frontend data-contract changes** for the live data —
  the existing cards light up automatically as fields populate.
- Avoids a schema migration and avoids two parallel sources of truth.
- The `_RESULT_FIELDS` snapshot already produced at `brain_service.py:143` is the
  exact payload to write.

Consequence: `AgentRunResult` (the typed `result` schema) must gain the
**Phase-1/decide/validate fields** that are currently produced but dropped, so they
survive the round-trip and can be displayed (see API Changes). The unused
`AgentRunOut.execution_snapshot` field is **removed** to eliminate the dead
contract.

No new columns. No new tables. No migration required (JSONB is schemaless).

---

## Retrieval Changes

No retrieval changes. `relevant_chunks` may optionally be surfaced in the UI as a
"Context Retrieved" card, but that is listed as a stretch item, not a requirement,
and reads from existing state.

---

## API Changes

No new endpoints. The existing `GET /agent-runs/{run_id}` (polled every 2 s by the
frontend) now returns a progressively-populated `result` instead of `null` until
completion.

### Schema change — `AgentRunResult` (`apps/api/app/schemas/agent_run.py`)

Extend the serialized result subset so live outputs that already exist in
`accumulator` survive into the API response:

```python
class AgentRunResult(BaseModel):
    # existing
    selected_issue: dict | None = None
    plan: dict | None = None
    code_changes: list[dict] = []
    review: dict | None = None
    pull_request_draft: dict | None = None
    pull_request_url: str | None = None
    pull_request_number: int | None = None
    iteration: int | None = None
    repair_context: dict | None = None
    # new — produced by the graph today but dropped before reaching the UI
    repo_context: dict | None = None
    issue_analyses: list[dict] = []
    validation_result: dict | None = None
    test_results: list[dict] = []
    patch_results: list[dict] = []
```

### Schema change — `AgentRunOut`

Remove the dead `execution_snapshot: dict | None` field (never populated; replaced
by the live `result`).

### `_RESULT_FIELDS` (`brain_service.py`)

Add the new fields so the per-node snapshot serializes them:
`repo_context`, `issue_analyses`, `validation_result`, `test_results`
(`patch_results` is already present).

### Request / Response shape

`GET /agent-runs/{run_id}` request: unchanged. Response: same `AgentRunOut`, but
`result` is non-null and grows across polls while `status == "running"`.

---

## Frontend Changes

All changes in `apps/web/src/components/agents/agent-run-detail.tsx` plus small new
presentational components. No new pages.

### Behavior

- The existing poll loop already calls `setRun(data)` every 2 s. Because `result`
  now arrives incrementally, the existing output cards (`plan`, `changes`, `review`)
  begin rendering mid-run with **no logic change**. The work is presentation:
  reveal animation + new card types.

### Components (new)

- `OutputCard` — shared wrapper: icon, title, "just arrived" entrance animation
  (fade + slide-up, ~200 ms, respecting `prefers-reduced-motion`). Used by all
  output sections so each agent's result visibly "lands."
- `IssueAnalysisCard` — renders `selected_issue` + the matching entry from
  `issue_analyses`: issue type, severity badge, confidence bar, impact bar,
  estimated complexity, selection reasoning.
- `PlanCard` — extend the existing inline plan block to also show
  `affected_files` (as file chips) and `dependencies`, not just tasks +
  `approach_reasoning`.
- `ReviewCard` — extend the existing review block to render `security_issues`
  (red), `suggestions` (amber), and the approved/changes-requested verdict, not
  just `comments`.
- `PrDraftCard` — when `pull_request_draft` exists but a real PR URL does not yet,
  show the draft title + a collapsed markdown body preview, so the PR stage has
  visible output before/instead of the "View Pull Request" button.

### Components (reuse)

- `DiffViewer` — already streams per-file diffs; no change. Diffs now appear as
  soon as `code_changes` lands mid-run.

### Visualizations

- Confidence / impact rendered as thin horizontal meter bars (0–1).
- Severity / issue-type / complexity as colored pill badges.

### Activity feed

- Extend the feed so each newly-populated `result` field appends a timestamped
  line as it arrives (analysis done, plan ready, N files changed, review verdict,
  PR draft ready) — driven by field presence, matching the existing pattern at
  `agent-run-detail.tsx:289-298`.

### State management

- None added. Continues to use the existing local `useState`/`useEffect` poll.

---

## Files To Modify

- `apps/api/app/schemas/agent_run.py` — extend `AgentRunResult`; remove
  `AgentRunOut.execution_snapshot`.
- `apps/api/app/services/brain_service.py` — add new fields to `_RESULT_FIELDS`;
  persist the per-node snapshot into `result` on each stream update (call
  `update_status(..., result=snapshot)` inside the existing loop at lines 146-151).
- `apps/web/src/components/agents/agent-run-detail.tsx` — add new output cards,
  reveal animation, extended plan/review rendering, richer activity feed.
- `apps/web/src/lib/api.ts` — extend the `AgentRunResult` TypeScript type to mirror
  the new backend fields; drop `execution_snapshot` from `AgentRunOut`.

## Files To Create

- `apps/web/src/components/agents/output-card.tsx` — shared animated card wrapper.
- `apps/web/src/components/agents/issue-analysis-card.tsx`
- `apps/web/src/components/agents/pr-draft-card.tsx`

(Plan/Review extensions stay inline in `agent-run-detail.tsx` since they extend
existing blocks; promote to files only if they grow large.)

---

## New Packages

No new packages. Entrance animations use existing Tailwind utilities / CSS; do not
add a motion library. (If a shared animation primitive is ever needed, prefer
`tailwindcss-animate`, which shadcn/ui already pulls in — confirm before adding.)

---

## Implementation Rules

- TypeScript strict mode; no `any` without justification (the existing
  `*Shape` interfaces in `agent-run-detail.tsx` are the typing pattern to follow).
- Backend contracts via Pydantic schemas only; extend `AgentRunResult`, never pass
  raw dicts to the route.
- No business logic in API routes — the snapshot-persistence logic stays in
  `BrainService`, not in `agent_runs.py`.
- Repository/service pattern preserved: persistence goes through
  `agent_run_repo.update_status`.
- Targeted edits only; preserve the existing card layout, color system, and the
  `NODE_TO_STAGE` source-of-truth from Spec 14.
- Never expose `github_pat`; the snapshot must only contain `_RESULT_FIELDS`
  (no PAT, no `git_result` secrets) — verify the serialized payload.
- LangGraph state stays fully typed; no state-shape changes in this spec.
- Respect `prefers-reduced-motion` for all entrance animations.

---

## Definition Of Done

- [ ] `GET /agent-runs/{run_id}` returns a non-null `result` while `status` is
      `running`, and the populated fields grow across successive polls.
- [ ] `AgentRunResult` includes `repo_context`, `issue_analyses`,
      `validation_result`, `test_results`, `patch_results`; `execution_snapshot` is
      removed from `AgentRunOut`.
- [ ] The per-node snapshot is persisted to `result` on every node transition in
      `BrainService.start()`, and contains no PAT / git secrets.
- [ ] Issue analysis card renders severity badge, confidence bar, impact bar, and
      selection reasoning as soon as `selected_issue` + `issue_analyses` arrive.
- [ ] Plan card renders tasks **and** affected files **and** dependencies.
- [ ] Code diffs appear mid-run as `code_changes` populates (not only at the end).
- [ ] Review card renders verdict, comments, security issues, and suggestions.
- [ ] PR draft card shows the draft title + body preview when a draft exists.
- [ ] Each output card plays a one-time entrance animation when it first appears,
      and animations are disabled under `prefers-reduced-motion`.
- [ ] Activity feed appends a timestamped line as each output field first appears.
- [ ] A full run watched from start shows outputs landing progressively; the
      completed view is unchanged from today's screenshot.
- [ ] No new endpoints, tables, columns, or packages were added.

---

## Architecture Impact

- **Affected systems:** `BrainService` (one extra DB write per node transition —
  ~8–12 small JSONB writes per run), the `agent_runs.result` column, and the agent
  detail UI. No change to the graph, agents, or vector store.
- **Dependencies introduced:** none.
- **Scalability concerns:** the extra per-node `UPDATE agent_runs SET result=...`
  writes are bounded by node count (small) and run in the same session already used
  for `current_node` updates — negligible. The frontend poll cadence is unchanged
  (2 s). For many concurrent runs this is the same write pattern as the existing
  `current_node` updates.
- **Future extensions:** swapping the 2 s poll for SSE/WebSocket streaming becomes
  trivial once outputs are persisted incrementally (the `_active_snapshots` map is
  already the in-memory source a stream endpoint would push from). A
  "Context Retrieved" card over `relevant_chunks` is a natural next card.

---

## Risks

- **Partial/inconsistent snapshots:** a snapshot written mid-loop may have, e.g.,
  `code_changes` but not yet `review`. The UI already treats every field as
  independently optional (presence-gated rendering), so this is safe by
  construction — but new cards must follow the same "render only if present"
  discipline.
- **Stale field from a prior iteration:** during the auto-repair loop a field
  (e.g. `review`) from iteration 1 may show while iteration 2 is mid-flight. Mitigate
  by keying the "repaired" indicator off `iteration` (already done) and labeling the
  review card with the iteration when `iteration > 1`.
- **Write amplification / DB load:** more frequent `result` writes. Mitigation: the
  payload is small JSONB and writes are already happening for `current_node`; fold
  the `result` update into that same `update_status` call rather than adding a
  second write.
- **Secret leakage into persisted `result`:** the snapshot must never include the
  PAT or `git_result` push details. Mitigation: snapshot is built strictly from
  `_RESULT_FIELDS`; add a test asserting no PAT-bearing fields are serialized.
- **LLM failure modes:** an agent may emit malformed/empty structured output (e.g.
  empty `issue_analyses`). Cards are presence-gated and must tolerate empty arrays
  and missing optional fields without throwing — render nothing rather than crash.
- **Animation jank on fast polls:** re-render every 2 s must not re-trigger entrance
  animations on already-visible cards. Mitigation: animate on first mount only
  (CSS one-shot / mount-keyed), not on every poll-driven re-render.
```