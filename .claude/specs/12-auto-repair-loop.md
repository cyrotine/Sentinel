# Spec: Auto Repair Loop

## Overview

Phase 7 makes Forge's feedback loops **actually repair**. Today the graph already routes
back to the developer when the validator fails or the reviewer rejects, and the `developer`
node increments `iteration` so the loops terminate at `max_iterations`. But two things are
missing, and both are the whole point of an "auto repair" loop:

1. **The patch-failure loop does not exist.** `apply_patches` always falls through to the
   validator regardless of whether `git apply` succeeded. The node's own docstring says so:
   *"Always proceeds to the validator regardless of patch outcome — acting on failures is
   Phase 7."* A diff that fails to apply is the single most common, most fixable failure in
   an LLM patching pipeline, and right now it is silently carried forward.

2. **The developer is re-invoked with identical inputs.** On every retry the `developer`
   node calls `agent.develop(plan, selected_issue, repo_context, retrieved_chunks,
   full_file_contexts)` — the exact same arguments as the first attempt. It is never told
   *why* it is being re-run. With temperature 0.2 the model regenerates almost the same diff,
   so the loop burns its iteration budget without converging. The loops are wired but inert.

Phase 7 closes both gaps:

- Add a `route_after_apply_patches` conditional edge that routes back to the developer when
  any patch failed to apply (and the iteration budget remains), feeding the failed diff +
  current on-disk file content back for regeneration.
- Introduce a typed `RepairContext` that the `developer` node assembles from the current
  state (failed `patch_results`, a failing `validation_result`, a rejecting `review`) and
  passes into `DeveloperAgent.develop()`. The developer prompt gains a "PREVIOUS ATTEMPT
  FAILED" section so the LLM corrects its specific mistakes instead of guessing again.

**Why it exists.** Autonomy means recovering from your own errors without a human. A single
malformed hunk should not doom a run. This phase turns three already-wired-but-dead edges
into a real self-correction loop, which is the difference between "Forge took one shot" and
"Forge iterated until it got it right (or ran out of budget and reported why)."

**How it contributes to autonomous engineering.** It is the *Decide → Act → Observe → Decide
again* cycle. Every prior phase produces an artifact; Phase 7 is the first that lets Forge
read its own failures and act on them.

---

## Depends On

- **Phase 4 — Patch Executor** (`09-patch-executor`): `PatchResult.applied`, `.failed_patch`,
  `.full_file_content` — the failure context the repair loop feeds back to the developer.
- **Phase 3 — Full File Retrieval** (`08-full-file-retrieval`): `full_file_contexts`, the
  ground-truth file content the developer diffs against.
- **Existing**: `ValidatorAgent` (`validation_result.issues/suggestions`), `ReviewerAgent`
  (`review.comments/security_issues/suggestions`), and the `iteration` / `max_iterations`
  fields already present on `SentinelState`.

No new infrastructure. This phase is entirely within `graph.py`, `developer.py`, and `state.py`.

---

## User Story

As a repository owner, when Forge's first code attempt does not apply cleanly, fails
validation, or is rejected in review, I want Forge to automatically read its own failure,
fix the specific problem, and try again — up to a bounded number of attempts — so that a
small, recoverable mistake does not waste the entire run, and so the final result reflects
self-correction rather than a single lucky shot.

---

## Agent Changes

### Create

No new agent class.

### Modify

**`DeveloperAgent` (`packages/agents/forge_agents/developer.py`)**

Extend `develop()` with one new optional keyword argument:

```python
async def develop(
    self,
    *,
    plan: Plan,
    selected_issue: SelectedIssue,
    repo_context: RepoContext,
    retrieved_chunks: list[RetrievedChunk],
    full_file_contexts: list[FullFileContext],
    repair_context: RepairContext | None = None,   # NEW
) -> list[CodeChange]:
```

Responsibilities of the change:
- When `repair_context is None` (first attempt), behavior is **byte-for-byte unchanged**.
- When `repair_context` is present, `_build_prompt` prepends a **"PREVIOUS ATTEMPT FAILED"**
  section describing exactly what went wrong, so the model regenerates a corrected diff.
- The new section is built by a private helper `_build_repair_block(repair_context)` and is
  the *first* thing after the role line so it dominates the model's attention.

The default argument keeps every existing caller and test working without modification.

---

## Workflow Changes

### Inputs

The `developer` node already reads full `SentinelState`. Phase 7 makes it additionally read
the failure signals that are already in state but currently ignored:
- `state.patch_results` — failed patches (`applied is False`) with `failed_patch` + `full_file_content`
- `state.validation_result` — when `passed is False`: `issues`, `suggestions`
- `state.review` — when `approved is False`: `comments`, `security_issues`, `suggestions`

### Outputs

- `developer` node additionally returns `repair_context` (the `RepairContext` it built, or
  `None` on the first attempt) so the loop reason is observable in streamed state and
  persisted to `AgentRun.result`.

### State Changes

New model `RepairContext` and one new field on `SentinelState`:

```python
class RepairContext(BaseModel):
    """Why the developer is being re-invoked, assembled from the prior attempt's failures.

    Built by the `developer` node from existing state fields on retry iterations.
    Carries the minimum the LLM needs to correct its specific mistakes.
    """
    iteration: int
    triggers: list[str]                       # any of: "patch_failed", "validation_failed", "review_rejected"
    failed_patches: list[PatchResult] = []    # only PatchResults with applied is False
    validation_issues: list[str] = []
    validation_suggestions: list[str] = []
    review_comments: list[str] = []
    review_security_issues: list[str] = []
    review_suggestions: list[str] = []
```

Added to `SentinelState` (Phase 5 — Execute group, next to `patch_results`):

```python
repair_context: RepairContext | None = Field(
    default=None,
    description="Failure feedback fed to the developer on the current retry iteration; None on first attempt",
)
```

`max_iterations` (default 3) and `iteration` are reused as-is — they remain the **single
shared budget** across all three loops. No new counters.

### Graph Nodes

No new nodes. The `developer` and `apply_patches` node bodies change:

- **`developer`**: before calling the agent, build `repair_context` via a pure helper
  `_build_repair_context(state)` that returns `None` on the first attempt (iteration 0 with
  no failure signals) or a populated `RepairContext` otherwise. Pass it to `agent.develop()`
  and include it in the returned state dict.

- **`apply_patches`**: unchanged logic (rollback → apply_all), but its docstring is updated —
  it no longer claims "acting on failures is Phase 7"; failure routing now lives in the new
  conditional edge.

### Graph Edges

**Replace** the unconditional `APPLY_PATCHES → VALIDATOR` edge with a conditional edge:

```python
def route_after_apply_patches(state: SentinelState) -> Literal["developer", "validator"]:
    """Route back to the developer when any patch failed to apply and budget remains."""
    results = state.patch_results
    any_failed = any(not r.applied for r in results)
    if any_failed and state.iteration < state.max_iterations:
        logger.info(
            "Patch application failed (iteration %d) — routing back to developer",
            state.iteration,
        )
        return DEVELOPER
    return VALIDATOR
```

Wiring:

```python
graph.add_edge(DEVELOPER, APPLY_PATCHES)
graph.add_conditional_edges(
    APPLY_PATCHES,
    route_after_apply_patches,
    {DEVELOPER: DEVELOPER, VALIDATOR: VALIDATOR},
)
```

The existing `route_after_validator` (validator → developer / test_agent) and
`route_after_reviewer` (reviewer → developer / pr_generator) are **kept unchanged** — they
already gate on `iteration < max_iterations`. They simply become effective now that the
developer receives repair feedback.

Resulting topology (changed segment in **bold**):

```
… → planner → developer → apply_patches
                              │  (route_after_apply_patches)
                              ├─ patch failed & budget left → developer   ← NEW
                              └─ applied or budget spent     → validator
   validator → (route_after_validator)
                ├─ invalid & budget left → developer
                └─ valid or budget spent → test_agent
   test_agent → reviewer → (route_after_reviewer)
                            ├─ rejected & budget left → developer
                            └─ approved or budget spent → pr_generator → END
```

### Termination guarantee

All three back-edges are gated by the same `state.iteration < state.max_iterations` check,
and `developer` increments `iteration` on every entry. With `max_iterations = 3` the
developer runs at most 4 times total (initial + 3 repairs) regardless of which loop fires.
The existing `_RECURSION_LIMIT = 50` backstop in `BrainService` remains as defense-in-depth.

---

## Database Changes

No new tables or columns. `repair_context` and `iteration` flow into the existing
`agent_runs.result` JSONB column via `BrainService` (see API Changes). The
`AgentRun.current_node` field already records loop re-entries through the existing
`stream_mode="updates"` persistence.

---

## Retrieval Changes

No retrieval changes. The repair loop reuses the chunks and full files already loaded in the
first iteration — `retrieve_context` and `load_full_files` are upstream of the developer and
are not re-run on a back-edge.

---

## API Changes

No new endpoints. Two additive, backward-compatible fields surface the loop in run results.

**`apps/api/app/services/brain_service.py`** — add `iteration` and `repair_context` to the
persisted result by extending `_RESULT_FIELDS`:

```python
_RESULT_FIELDS = (
    "selected_issue",
    "plan",
    "code_changes",
    "patch_results",
    "review",
    "pull_request_draft",
    "iteration",        # NEW — how many developer passes ran
    "repair_context",   # NEW — the last repair reason, or None if it converged first try
)
```

`iteration` is a plain int and `repair_context` is serialized by the existing `_dump`
helper (it is a Pydantic model), so no other serialization work is required.

**`apps/api/app/schemas/agent_run.py`** — `AgentRunResult`: add two nullable fields:

```python
iteration: int | None = None            # NEW
repair_context: dict | None = None      # NEW
```

---

## Frontend Changes

### Pages

No new pages.

### Components

**Modified: `apps/web/src/components/agents/agent-run-detail.tsx`**

Surface that self-correction happened. When `result.iteration` is greater than 1, render a
small "Repair" badge near the run status:

```
┌──────────────────────────────────────────────┐
│ DEVELOPER                                      │
│ ↻ Repaired · 2 attempts                        │
│ Last trigger: patch failed to apply            │
└──────────────────────────────────────────────┘
```

- Show the badge only when `result.iteration` is present and `> 1`.
- When `result.repair_context` is non-null, show `repair_context.triggers` joined as a
  human-readable reason (e.g. "patch failed to apply", "validation failed", "review rejected").
- This is read-only display; no new interactions.

**Modified: `apps/web/src/lib/api.ts`** — update the `AgentRunResult` interface:

```typescript
export interface AgentRunResult {
  // …existing fields…
  iteration: number | null            // NEW
  repair_context: Record<string, unknown> | null  // NEW
}
```

### Visualizations

No new visualizations. (A future enhancement could highlight the back-edges in the workflow
graph when a repair occurred — out of scope here.)

### Dashboard Modules

No dashboard changes.

### State Management

Local `useState` only. No global state library introduced.

---

## Files To Modify

```
packages/workflows/forge_workflows/state.py
    Add RepairContext model.
    Add repair_context: RepairContext | None field to SentinelState.

packages/workflows/forge_workflows/graph.py
    Add route_after_apply_patches() conditional routing function.
    developer node: build RepairContext from state via _build_repair_context(state);
        pass repair_context into agent.develop(); return it in the state dict.
    apply_patches node: replace the unconditional edge to VALIDATOR with the conditional edge;
        update the docstring (remove the "acting on failures is Phase 7" note).
    Wire add_conditional_edges(APPLY_PATCHES, route_after_apply_patches, …).

packages/agents/forge_agents/developer.py
    develop(): add repair_context: RepairContext | None = None parameter.
    _build_prompt(): accept repair_context; prepend the repair block when present.
    Add _build_repair_block(repair_context) -> str helper.
    Import RepairContext from forge_workflows.state.

apps/api/app/services/brain_service.py
    Extend _RESULT_FIELDS with "iteration" and "repair_context".

apps/api/app/schemas/agent_run.py
    AgentRunResult: add iteration and repair_context fields.

apps/web/src/lib/api.ts
    AgentRunResult interface: add iteration and repair_context.

apps/web/src/components/agents/agent-run-detail.tsx
    Render a "Repaired · N attempts" badge + last-trigger reason when iteration > 1.
```

---

## Files To Create

No new source files. Phase 7 is a behavioral change to existing nodes and the developer
prompt, not new infrastructure.

(New test files only — see Definition Of Done.)

---

## New Packages

No new packages.

---

## Implementation Notes

### Where `RepairContext` is assembled — in the node, not the router

LangGraph routing functions are **pure** and cannot write state. So the `RepairContext` is
built inside the `developer` node from signals already on `state`, not inside the routing
functions. A pure helper keeps the node thin:

```python
def _build_repair_context(state: SentinelState) -> RepairContext | None:
    failed = [r for r in state.patch_results if not r.applied]
    vr = state.validation_result
    rev = state.review

    triggers: list[str] = []
    if failed:
        triggers.append("patch_failed")
    if vr is not None and not vr.passed:
        triggers.append("validation_failed")
    if rev is not None and not rev.approved:
        triggers.append("review_rejected")

    # First attempt (or a clean re-entry with no failure signal): no repair context.
    if not triggers:
        return None

    return RepairContext(
        iteration=state.iteration,
        triggers=triggers,
        failed_patches=failed,
        validation_issues=vr.issues if (vr and not vr.passed) else [],
        validation_suggestions=vr.suggestions if (vr and not vr.passed) else [],
        review_comments=rev.comments if (rev and not rev.approved) else [],
        review_security_issues=rev.security_issues if (rev and not rev.approved) else [],
        review_suggestions=rev.suggestions if (rev and not rev.approved) else [],
    )
```

Guard in the node: only call this when `state.iteration > 0`; on the first pass it returns
`None` and the prompt is unchanged.

### The repair prompt block (developer.py)

`_build_repair_block` produces a section the model cannot ignore. For patch failures it must
include, per failed file, the **failed diff** and the **current on-disk content** so the
model re-diffs against ground truth:

```
PREVIOUS ATTEMPT FAILED — fix the specific problems below, then regenerate ALL changes.

Trigger(s): patch_failed

The following patch(es) did NOT apply cleanly:

  ### path/to/file.html
  Reason: error: patch failed: path/to/file.html:12
  Your previous (rejected) diff:
  ```
  <the failed_patch verbatim>
  ```
  Current on-disk content (diff against THIS — line numbers are exact):
  ```
  <full_file_content>
  ```

Validation issues to resolve:
  - <issue 1>
Suggestions:
  - <suggestion 1>

Review feedback to address:
  - <comment / security issue / suggestion>

Regenerate corrected unified diffs for every affected file. Do not repeat the rejected diff.
```

`apply_patches` rolls the workspace back to a pristine clone before each apply, so the
regenerated diffs must always be expressed against the *original* file content — which is
exactly what `full_file_content` (read after rollback context) and `full_file_contexts`
provide. The block must instruct the model to diff against the original, not against a
half-applied tree.

### Single shared iteration budget

Do **not** add per-loop counters. One `iteration` counter shared across all three back-edges
is intentional: it bounds total developer work regardless of which failure mode recurs. A run
that fails patch application twice then fails review once has used 3 of 3 and proceeds to PR
generation with whatever it has. This matches the roadmap ("Stop after `max_iterations`").

### `apply_patches` already rolls back — keep it

The existing `rollback_all` → `apply_all` sequence in `apply_patches` is what makes the loop
safe: each retry re-applies the latest full diff set against a clean tree, so there is no
patch-on-patch drift. Phase 7 does not change this; it only adds the routing decision after it.

---

## Implementation Rules

- Routing functions stay **pure** — no state writes, no side effects, no injected deps.
- `RepairContext` is a Pydantic model; no raw dicts pass between nodes (CLAUDE.md state rule).
- LangGraph state stays fully typed — `repair_context` is a typed optional field.
- `develop()`'s new parameter is **optional with a default** — first-attempt behavior and all
  existing callers/tests remain unchanged.
- No business logic in API route handlers — result assembly stays in `BrainService`.
- Targeted edits only; preserve the existing node structure and the existing two conditional
  edges. Do not refactor the graph beyond adding the third edge and the developer feedback.
- TypeScript strict mode; no `any` without justification.
- The repair block must never include secrets — it only echoes diffs and file content already
  present in the workspace; no PAT, no credentials.

---

## Definition Of Done

- [ ] `RepairContext` model added to `state.py` with all listed fields, fully typed.
- [ ] `SentinelState.repair_context: RepairContext | None` field added (default `None`).
- [ ] `route_after_apply_patches` added; returns `DEVELOPER` only when a patch failed **and**
      `iteration < max_iterations`, else `VALIDATOR`.
- [ ] `APPLY_PATCHES → VALIDATOR` unconditional edge replaced by the conditional edge.
- [ ] `developer` node builds `RepairContext` via `_build_repair_context(state)` and returns
      it in the state dict; returns `None` on the first attempt.
- [ ] `developer` node passes `repair_context` into `DeveloperAgent.develop()`.
- [ ] `DeveloperAgent.develop()` accepts `repair_context` (optional, default `None`); first-pass
      prompt is unchanged when it is `None`.
- [ ] On retry, the developer prompt contains a "PREVIOUS ATTEMPT FAILED" section listing the
      failed diff + current file content for each failed patch, plus validation/review feedback.
- [ ] A run whose first developer diff fails to apply re-enters the developer, regenerates, and
      applies cleanly on the second attempt (verified on a 2–3 file HTML repo).
- [ ] The loop stops after exactly `max_iterations` developer re-entries; the run still
      completes (`status = completed`) and proceeds to PR generation with the best result.
- [ ] All three back-edges (patch / validator / reviewer) share the single `iteration` budget.
- [ ] `_RESULT_FIELDS` includes `iteration` and `repair_context`; both appear in `AgentRun.result`.
- [ ] `AgentRunResult` backend schema and TS interface both gain `iteration` and `repair_context`.
- [ ] `agent-run-detail.tsx` shows a "Repaired · N attempts" badge with the last trigger when
      `iteration > 1`; nothing extra renders when the run converged on the first pass.
- [ ] Unit tests: `route_after_apply_patches` (failed+budget → developer; applied → validator;
      failed+exhausted → validator); `_build_repair_context` (None on first pass, populated per
      trigger); `_build_repair_block` includes the failed diff and file content.

---

## Architecture Impact

**Affected systems:**
- `packages/workflows/forge_workflows/graph.py` — one new conditional edge + developer feedback assembly.
- `packages/workflows/forge_workflows/state.py` — additive: one model, one field.
- `packages/agents/forge_agents/developer.py` — additive optional parameter + prompt branch.
- `apps/api` — additive result fields; no schema migration.
- Frontend — additive read-only badge.

**Dependencies introduced:** None. Every input the repair loop consumes (`PatchResult`,
`ValidationResult`, `Review`, `full_file_contexts`) already exists from Phases 3–6.

**Scalability concerns:**
- Each repair iteration is one additional LLM call to the developer (plus the re-run validator/
  reviewer on its branch). Worst case is `max_iterations` extra developer+validator+reviewer
  passes — bounded, and small for the HTML MVP target. Token cost scales with file size, which
  is tiny for the 30–40-line target repos.
- The repair prompt embeds full file content; for large files this grows the prompt. Acceptable
  for the current MVP profile; a future phase can switch to hunk-local context for big files.

**Future extensions:**
- Per-trigger iteration budgets (e.g. allow more patch retries than review retries).
- Feed the *successful* strategy (`git-apply-3way`) back as a hint.
- Push repair commits to the same branch/PR (ties into Phase 6's "additional commits" note)
  instead of regenerating from a clean tree once a real PR already exists.
- Surface the full repair history (every iteration's trigger) in the Execution Timeline graph.

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| LLM regenerates the *same* failing diff, wasting the budget | Medium | Prompt explicitly says "Do not repeat the rejected diff" and supplies current on-disk content to diff against; temperature stays low but the failure context changes the input materially. Budget caps the cost at `max_iterations`. |
| Repair prompt grows large for big files | Low (MVP is 30–40-line files) | Acceptable for the HTML target; flag hunk-local context as a future optimization. |
| A non-deterministic failure flaps (passes, then fails on re-run) | Low | `apply_patches` rolls back to a pristine clone each pass, removing patch-on-patch drift; routing is gated by the iteration counter so flapping cannot loop forever. |
| Reviewer/validator keep rejecting valid changes, exhausting budget every run | Medium | Loop terminates at `max_iterations` and still completes; the run surfaces `repair_context` so a human sees *why* it could not converge. Tune `max_iterations` per repo if needed. |
| `iteration` shared across loops masks which loop dominated | Low | `repair_context.triggers` records the active failure mode each pass; persisted to `AgentRun.result` and shown in the UI badge. |
| Existing developer tests break from the signature change | Low | New parameter is optional with a default; first-attempt behavior is byte-for-byte unchanged. Add new tests rather than altering existing ones. |