# Spec: Test Gen Pipeline Stage

## Overview

The backend LangGraph pipeline (`packages/workflows/forge_workflows/graph.py`) already
has a `test_designer` node that runs **between `planner` and `developer`** — implementing
true TDD by authoring executable `TestSpec`s before code is written. However, the
frontend execution pipeline visualization in `agent-run-detail.tsx` does not reflect
this: it maps `test_designer` to the existing `"testing"` stage (which represents
post-code test *execution*), collapsing two distinct phases into one misleading label.

This spec adds a dedicated **Test Gen** step to the pipeline UI, positioned between
Planning and Code Gen, so the visualization accurately mirrors the backend graph order:

```
Issue Selected → Planning → Test Gen → Code Gen → Testing → Review → Pull Request
```

This is a **frontend-only change**. No backend, database, vector store, or workflow
modifications are needed — the `test_designer` node already exists and produces
`test_specs` in the run result.

---

## Depends On

- Spec 16 — Real Local Test Execution (the `test_designer` node and `test_specs` state
  field this spec surfaces in the UI)

---

## User Story

As a developer watching Forge work autonomously, I want to see the pipeline clearly
distinguish "designing tests from acceptance criteria" (Test Gen) from "running those
tests against generated code" (Testing), so I understand exactly what Forge is doing
at each step and can debug a stuck or failed run with precision.

---

## Agent Changes

No agent changes. The `TestDesignerAgent` already exists at
`packages/agents/forge_agents/test_designer.py`.

---

## Workflow Changes

No workflow changes. The `test_designer` → `developer` edge already exists in
`packages/workflows/forge_workflows/graph.py` (line 571).

---

## Database Changes

No database changes.

---

## Retrieval Changes

No retrieval changes.

---

## API Changes

No API changes. The `test_specs` field is already returned in `AgentRunOut.result`
from the existing `/api/agent-runs/{id}` endpoint.

---

## Frontend Changes

### Files To Modify

**`apps/web/src/components/agents/agent-run-detail.tsx`**

#### 1. Extend `PipelineStage` union type (line 16)

Add `"test_designer"` to the type:

```ts
type PipelineStage =
  | "issue_selection"
  | "planner"
  | "test_designer"   // ← new
  | "developer"
  | "testing"
  | "reviewer"
  | "pull_request"
```

#### 2. Update `NODE_TO_STAGE` map (line 22)

Remap `test_designer` from `"testing"` to `"test_designer"`:

```ts
const NODE_TO_STAGE: Record<string, PipelineStage> = {
  repo_analyzer:    "issue_selection",
  issue_analyzer:   "issue_selection",
  retrieve_context: "issue_selection",
  load_full_files:  "issue_selection",
  planner:          "planner",
  test_designer:    "test_designer",   // was "testing"
  developer:        "developer",
  apply_patches:    "developer",
  validator:        "developer",
  test_agent:       "testing",
  reviewer:         "reviewer",
  pr_generator:     "pull_request",
}
```

#### 3. Add `isTestGenDone` derived state (near line 219)

```ts
const isTestGenDone = testSpecs.length > 0
```

#### 4. Update `activeStage` fallback chain (line 229)

Insert `"test_designer"` between `isPlanDone` and `isTestGenDone` in the result-presence
fallback:

```ts
const activeStage =
  isFailed ? "failed" :
  isPrDone  ? "completed" :
  liveStage ??
  (isReviewDone   ? "reviewer"      :
   isDevDone      ? "validator"     :
   isTestGenDone  ? "developer"     :
   isPlanDone     ? "test_designer" :
   isIssueDone    ? "planner"       :
   "issue_selection")
```

> When `test_specs` exist but `code_changes` do not yet, the fallback correctly
> infers the run is at the `test_designer` stage.

#### 5. Insert `PipelineStep` + `PipelineConnector` in the pipeline row (line 299)

Between the existing Planning step and the Code Gen step:

```tsx
<PipelineStep
  label="Test Gen"
  isActive={activeStage === "test_designer"}
  isCompleted={isTestGenDone}
/>
<PipelineConnector active={activeStage === "test_designer"} />
```

The resulting render order becomes:

```
Issue Selected → Planning → Test Gen → Code Gen → Testing → Review → Pull Request
```

#### 6. Activity Feed log entry (line 323)

The existing activity feed already logs test specs:

```tsx
{testSpecs.length > 0 && (
  <ActivityLogItem
    message={`Designed ${testSpecs.length} executable test${testSpecs.length === 1 ? "" : "s"} from acceptance criteria.`}
  />
)}
```

No change needed here — it will continue to fire when `testSpecs` arrives.

---

## Files To Modify

| File | Change |
|------|--------|
| `apps/web/src/components/agents/agent-run-detail.tsx` | Extend `PipelineStage` type, remap `NODE_TO_STAGE`, add `isTestGenDone`, update fallback chain, insert `PipelineStep`+`PipelineConnector` |

---

## Files To Create

None.

---

## New Packages

None.

---

## Implementation Rules

- TypeScript strict mode — no `any`
- Targeted edits only — touch nothing outside the pipeline section
- Do not alter the activity feed ordering
- Do not change any backend file

---

## Definition Of Done

- [ ] Pipeline shows 7 steps: Issue Selected → Planning → Test Gen → Code Gen → Testing → Review → Pull Request
- [ ] While `test_designer` node is active (`run.current_node === "test_designer"`), the Test Gen step shows the spinning loader and the Planning step is completed
- [ ] After `test_designer` finishes (`test_specs.length > 0`), the Test Gen step shows the blue checkmark
- [ ] While `developer` / `apply_patches` / `validator` nodes are active, the Code Gen step is active and Test Gen is completed
- [ ] The existing Testing step (`test_agent` node) is unaffected — it still activates and completes as before
- [ ] A run with no `test_specs` (e.g. old completed run) renders gracefully with Test Gen in the uncompleted/inactive state
- [ ] No TypeScript errors (`pnpm tsc --noEmit` passes in `apps/web`)

---

## Architecture Impact

**Affected systems:** Frontend only (`apps/web`).

**Dependencies introduced:** None.

**Scalability:** The pipeline step list is hardcoded; adding further nodes in the future
will require the same targeted edit pattern. This is acceptable for the current MVP scope.

**Future extensions:** When Phase 10 (Docker sandbox) adds more execution nodes, the same
`NODE_TO_STAGE` map and pipeline row can be extended incrementally.

---

## Risks

| Risk | Mitigation |
|------|------------|
| Old completed runs that pre-date `test_designer` have no `test_specs` | `isTestGenDone = testSpecs.length > 0` defaults to `false`, rendering Test Gen as uncompleted — visually correct |
| `activeStage` fallback inference is order-sensitive | The new fallback chain is explicitly ordered: `isDevDone` is checked before `isTestGenDone`, so the stages never regress |
| Pipeline row becomes too wide for small viewports | The pipeline already uses `justify-between` with `flex-1` connectors; adding one step reduces each connector's width proportionally — acceptable at the existing max-width |
