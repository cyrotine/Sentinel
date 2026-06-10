# Spec: Patch Executor

## Overview

The Patch Executor applies the unified diffs produced by the `DeveloperAgent` to the
real files in the cloned workspace on disk. Until this phase, `CodeChange.patch` is a
text artifact: it is generated, rendered in the UI (Phase 1), and reasoned about by the
Validator/Reviewer — but it is never actually applied to a file. This phase is the first
time Forge **mutates the working tree**.

**Why it exists.** The critical path to a real pull request is
`workspace → patch → git → PR`. Phase 2 gave us a cloned workspace; Phase 3 gave the
Developer full file contents so its diffs have correct context. Phase 4 closes the loop:
take the generated diff and make it real on disk. Without it, Phase 5 (git commit) has
nothing to stage and Phase 6 (PR creation) has nothing to push.

**How it contributes to autonomous engineering.** Applying a patch is the concrete
"Act" step (Think → Decide → **Act**). It also produces the ground-truth signal the whole
auto-repair loop depends on: *did the change the Developer proposed actually apply?* A
patch that fails to apply is the earliest, cheapest, most objective failure signal in the
pipeline — long before tests or review. Surfacing it (rather than silently swallowing it)
is what lets Phase 7 route a failed patch back to the Developer with the real file and the
broken diff.

---

## Depends On

- **Phase 2 — Repository Workspace** (`07-repository-workspace`): `state.workspace_path`
  must point at a cloned repo. No workspace, nothing to patch.
- **Phase 3 — Full File Retrieval** (`08-full-file-retrieval`): full file context is what
  makes Developer diffs apply cleanly and is reused to build retry feedback when they do
  not. `FileLoader` is the structural precedent this phase mirrors.

This phase does **not** depend on Phase 5 (Git) or Phase 7 (Auto Repair Loop). It produces
the `PatchResult` signal those phases consume, but it ships and is testable on its own. The
conditional retry edge is explicitly Phase 7's responsibility — see *Out of Scope*.

---

## User Story

As a repository owner, I want Forge to actually apply its generated code changes to the
files in its workspace — and to tell me exactly which patches applied and which failed and
why — so that the downstream git commit operates on real modifications and a failed patch
becomes an actionable repair signal instead of a silent no-op.

---

## Architectural Decision (resolved)

The roadmap names `apps/api/app/services/patch_executor.py`. That location is **not** used.

`graph.py` is application-agnostic — it imports nothing from `app.*` — and Phase 7 requires
patch application to run as a **graph node** so a failed patch can route back to the
Developer. Therefore the executor must be importable by `graph.py`. The Phase 3 `FileLoader`
established the pattern: a pure filesystem utility in `packages/agents/forge_agents/`, with
no DB and no config dependency, instantiated as a module-level singleton and called by a
deterministic graph node.

`PatchExecutor` follows that pattern exactly. It lives at
`packages/agents/forge_agents/patch_executor.py`. (Confirmed with the project owner; this
supersedes the roadmap's stated path for the same reasons Phase 3's `FileLoader` did.)

---

## Agent Changes

### Create

**`PatchExecutor`** — `packages/agents/forge_agents/patch_executor.py`

A deterministic filesystem + git utility (not LLM-powered). Applies a single
`CodeChange.patch` to the workspace and reports the result.

Responsibilities:
- Apply one `CodeChange` (a unified diff) to its target file in `workspace_path`.
- Detect cleanly-applied vs failed application.
- On success: report the file path and that it was modified.
- On failure: report the error and return the **current full file content** plus the
  **failed patch** so the caller (Phase 7) can ask the Developer to regenerate.
- Roll back all modifications in the workspace (`rollback_all`).
- Never raise on a bad patch — a failed application is a normal, reported outcome, not an
  exception. Reserve raised exceptions for genuinely broken inputs (missing workspace).

```python
class PatchExecutor:
    def apply_patch(self, workspace_path: str, code_change: CodeChange) -> PatchResult: ...
    def apply_all(self, workspace_path: str, code_changes: list[CodeChange]) -> list[PatchResult]: ...
    def rollback_all(self, workspace_path: str) -> None: ...
```

No `__init__` dependencies. Instantiate once as a module-level singleton:
`patch_executor = PatchExecutor()`.

**Patch application mechanism.** Apply diffs with `git` against the cloned workspace (the
workspace is already a git repo from Phase 2's clone), shelling out via `subprocess` in a
thread. Strategy, in order, stopping at the first that succeeds:

1. `git apply --check <patch>` then `git apply <patch>` — strict, exact-context apply.
2. `git apply --3way <patch>` — uses blob context to apply fuzzy/shifted hunks.
3. Fall back to a recoverable failure if both reject the patch.

Run all `git` invocations with `cwd=workspace_path`. Feed the patch via stdin
(`git apply -` ) to avoid temp-file path issues. Do **not** use `-p0/-p1` guessing beyond
git's default; the Developer is instructed to emit `a/`…`b/` prefixes (standard `git diff`
format), which `git apply` expects by default.

> Rationale: `git apply` is already available (GitPython is a dependency and git is on the
> host), understands standard unified-diff prefixes, has a dry-run (`--check`), and `--3way`
> gives one cheap fuzzy retry before we spend an LLM iteration. No new dependency needed.

This is **not** code execution. It is text-diff application to static files; the Docker
sandbox rule (deferred, per CLAUDE.md) does not apply.

### Modify

No existing agent is modified in this phase. The `DeveloperAgent` already emits
`CodeChange.patch` in standard unified-diff format (Phase 3) and needs no signature change
to be patch-applied. (Phase 7 will pass `PatchResult` feedback back into `develop()`; that
signature change belongs to Phase 7, not here.)

---

## Workflow Changes

### Inputs

- `state.workspace_path` — absolute path to the cloned repo (set by `BrainService`, Phase 2).
- `state.code_changes` — `list[CodeChange]` produced by the `developer` node.

### Outputs

- `state.patch_results` — `list[PatchResult]`, one per attempted `CodeChange`.

### State Changes

Add to `packages/workflows/forge_workflows/state.py`:

**New model:**

```python
class PatchResult(BaseModel):
    """Outcome of applying a single CodeChange to the workspace."""

    file_path: str = Field(..., description="Relative path of the patched file")
    applied: bool = Field(..., description="Whether the patch applied cleanly")
    strategy: str = Field(
        default="",
        description="How it applied: 'git-apply', 'git-apply-3way', or '' on failure",
    )
    error: str | None = Field(
        default=None, description="git stderr / failure reason when applied is False"
    )
    failed_patch: str | None = Field(
        default=None,
        description="The original unified diff that failed, echoed back for LLM retry",
    )
    full_file_content: str | None = Field(
        default=None,
        description="Current on-disk content of the target file, for LLM-regeneration context",
    )
```

**New field on `SentinelState`** (in the Phase 5 Execute block, immediately after
`code_changes`):

```python
patch_results: list[PatchResult] = Field(
    default_factory=list,
    description="Results of applying each CodeChange to the workspace",
)
```

**New `SentinelStatus` value** (between `DEVELOPING` and `VALIDATING`):

```python
APPLYING_PATCHES = "applying_patches"
```

`PatchResult` must be exported from `forge_workflows.state` (imported by `patch_executor.py`
and `graph.py`), exactly as `FullFileContext` is.

### Graph Nodes

**New node: `apply_patches`** in `packages/workflows/forge_workflows/graph.py`.

```python
APPLY_PATCHES = "apply_patches"

async def apply_patches(state: SentinelState) -> dict:
    # If workspace_path is None: warn, return empty patch_results (do not raise).
    # If no code_changes: warn, return empty patch_results.
    # Else: results = await asyncio.to_thread(
    #           patch_executor.apply_all, state.workspace_path, state.code_changes)
    # Return {"current_agent": APPLY_PATCHES,
    #         "status": SentinelStatus.APPLYING_PATCHES,
    #         "patch_results": results}
```

- Import the singleton: `from forge_agents.patch_executor import patch_executor`
  (mirrors `from forge_agents.file_loader import file_loader`).
- `PatchExecutor` is synchronous (subprocess/filesystem); wrap the call in
  `asyncio.to_thread` so it does not block the event loop — same reasoning as
  `WorkspaceManager.clone`.
- Add `APPLY_PATCHES` to the node-name constants block at the top of `graph.py`.

### Graph Edges

Replace the existing edge:

```
developer → validator
```

With:

```
developer → apply_patches → validator
```

The `validator` node is otherwise unchanged: it still reads `state.code_changes`. (The
Validator may *optionally* consult `state.patch_results` to ground its judgment in whether
the patch actually applied, but that enhancement is not required by this phase.)

> **Interaction with the existing retry loop.** `route_after_validator` and
> `route_after_reviewer` already route back to `DEVELOPER`. Because `apply_patches` sits on
> the `developer → validator` edge, every developer retry now re-applies patches before
> validation — which is correct. The *new* "route back on patch failure" edge
> (`apply_patches → developer`) is **Phase 7's** responsibility and is intentionally not
> added here; in this phase `apply_patches` always proceeds to `validator`.

### Idempotency / re-application on retry

When the loop re-enters `developer` and produces a fresh set of `code_changes`,
`apply_patches` runs again on the same workspace. Patches already applied in a prior
iteration would now fail to re-apply (the change is already present). To keep retries
deterministic, `apply_patches` calls `patch_executor.rollback_all(workspace_path)` at the
**start** of the node (resetting the working tree to the clean clone via
`git checkout -- .` + `git clean -fd`) before applying the current `code_changes`. This
guarantees each iteration applies the latest full set of diffs against a pristine tree.

---

## Database Changes

No database changes.

`PatchResult` flows through `SentinelState` only. `BrainService._RESULT_FIELDS` **may**
optionally add `"patch_results"` so the applied/failed outcome is persisted into
`AgentRun.result` for the UI — this is a one-line, low-risk addition and is listed under
*Files To Modify* as optional. No schema/migration is involved (the column is the existing
JSON `result` blob).

---

## Retrieval Changes

No Qdrant changes. `PatchExecutor` reads and writes the filesystem only.

---

## API Changes

No new endpoints. No changes to existing request/response schemas.

If `patch_results` is added to `AgentRun.result` (optional, above), it appears inside the
already-serialized `result` JSON returned by the existing agent-run detail endpoint — no
new field on any response model, no contract change.

---

## Frontend Changes

None required for this phase.

Optional (defer to a UI pass): the agent-run detail view could render a per-file
applied/failed badge from `patch_results`. Not in scope here; listed only so it is not
forgotten.

---

## Files To Modify

| File | Change |
|---|---|
| `packages/workflows/forge_workflows/state.py` | Add `PatchResult` model; add `patch_results` field on `SentinelState` (after `code_changes`); add `APPLYING_PATCHES` to `SentinelStatus` |
| `packages/workflows/forge_workflows/graph.py` | Add `APPLY_PATCHES` constant; add `apply_patches` node (imports `patch_executor` singleton, wraps call in `asyncio.to_thread`, rolls back then applies); replace edge `developer → validator` with `developer → apply_patches → validator`; update the module docstring topology diagram |
| `apps/api/app/services/brain_service.py` | *(Optional)* add `"patch_results"` to `_RESULT_FIELDS` so outcomes persist to `AgentRun.result` |

---

## Files To Create

| File | Purpose |
|---|---|
| `packages/agents/forge_agents/patch_executor.py` | `PatchExecutor` class + `patch_executor` singleton — applies unified diffs to the workspace via `git apply` (with `--3way` fuzzy fallback), returns `PatchResult` per change, supports `rollback_all` |

---

## New Packages

No new packages. Patch application uses the host `git` binary (already required by
GitPython/Phase 2) via `subprocess`; `subprocess`, `asyncio`, and `pathlib` are stdlib.
`PatchResult` reuses Pydantic (already a dependency).

---

## Implementation Rules

- All new models are Pydantic `BaseModel` subclasses; no raw dicts between nodes.
- `PatchExecutor` is a **pure** filesystem/git utility — no LLM, no database, no HTTP, no
  `app.*` imports. It may import `CodeChange`/`PatchResult` from `forge_workflows.state`
  (the existing one-way `agents → workflows.state` dependency).
- `PatchExecutor` must **never silently swallow a patch failure** (CLAUDE.md). A failed
  apply returns `PatchResult(applied=False, error=…, failed_patch=…, full_file_content=…)`.
- The `apply_patches` graph node must not raise on a missing workspace or empty
  `code_changes`; it degrades to an empty `patch_results` list and logs a warning (mirrors
  `load_full_files`).
- All `git`/subprocess work runs with `cwd=workspace_path`; the patch is fed via **stdin**,
  never written into the repo tree.
- Patches are applied to files **inside `workspace_path` only**. Reject (return a failed
  `PatchResult`) any `code_change.file_path` that resolves outside the workspace root after
  normalization (path-traversal guard).
- No Docker sandbox for this phase — diff application to static files is not code execution
  (per the CLAUDE.md HTML-phase carve-out).
- Synchronous executor calls from the async graph node go through `asyncio.to_thread`.
- `APPLY_PATCHES` is added to the node-name constants block; no stringly-typed node names.
- Type-checks cleanly (`mypy`/`pyright`): no untyped `list[PatchResult]`, no stray `Any`.

---

## Definition Of Done

- [ ] `PatchResult` model exists in `state.py` with `file_path`, `applied`, `strategy`, `error`, `failed_patch`, `full_file_content`.
- [ ] `SentinelState.patch_results` field exists, defaults to `[]`, sits after `code_changes`.
- [ ] `SentinelStatus.APPLYING_PATCHES` value exists.
- [ ] `PatchExecutor` class exists at `packages/agents/forge_agents/patch_executor.py` with `patch_executor` singleton.
- [ ] `apply_patch()` applies a clean unified diff to the real file in `workspace_path` and returns `applied=True` with `strategy` set.
- [ ] `apply_patch()` retries a shifted/fuzzy hunk via `git apply --3way` before declaring failure.
- [ ] On failure, `apply_patch()` returns `applied=False` with `error`, `failed_patch`, and the current `full_file_content` populated — and does **not** raise.
- [ ] A `file_path` resolving outside the workspace root yields a failed `PatchResult` (no write occurs).
- [ ] `apply_all()` returns one `PatchResult` per input `CodeChange`, preserving order.
- [ ] `rollback_all()` restores the workspace to the clean clone (tracked files reverted, untracked added-files removed).
- [ ] `apply_patches` graph node exists between `developer` and `validator`.
- [ ] `apply_patches` rolls back, then applies the current `code_changes`, then proceeds to `validator`.
- [ ] `apply_patches` returns empty `patch_results` (no raise) when `workspace_path` is `None` or `code_changes` is empty.
- [ ] Graph edge is `developer → apply_patches → validator`; the old `developer → validator` edge is removed.
- [ ] Executor calls are wrapped in `asyncio.to_thread`; the event loop is not blocked.
- [ ] `PatchResult` is exported from `forge_workflows.state` and imported by both `patch_executor.py` and `graph.py`.
- [ ] End-to-end on a static HTML repo: a Developer-generated typo/color/label fix is applied to the workspace file and `git diff` in the workspace shows the change.
- [ ] Type-checking passes with no new errors.

---

## Architecture Impact

**Affected systems:**
- `forge_agents`: new `PatchExecutor` utility (peer of `FileLoader`).
- `forge_workflows`: new `PatchResult` state model, new `APPLYING_PATCHES` status, new
  `apply_patches` node, one rewired edge.
- `BrainService`: unchanged behavior; optional one-line `_RESULT_FIELDS` addition.

**Dependencies introduced:**
- A runtime dependency on the host `git` binary for patch application. This already exists
  transitively (Phase 2 clones with GitPython, which requires git). No new Python package.
- `patch_executor.py` → `forge_workflows.state` (same direction `file_loader.py` already
  uses). No new dependency direction.

**Scalability concerns:**
- One `git apply` subprocess per `CodeChange`. For the HTML MVP (2–3 files) this is trivial.
  For large change sets the per-process overhead is acceptable; if it ever matters, multiple
  diffs can be concatenated into one `git apply` invocation. Not needed now.
- `rollback_all` via `git checkout -- . && git clean -fd` is O(working-tree); negligible for
  the target profile.

**Future extensions:**
- **Phase 5 (Git):** `GitService` stages exactly the files where `PatchResult.applied` is
  `True` — `patch_results` is the authoritative list of what actually changed on disk.
- **Phase 7 (Auto Repair Loop):** adds the conditional edge `apply_patches → developer` when
  any `PatchResult.applied` is `False`, feeding `failed_patch` + `full_file_content` back to
  `DeveloperAgent.develop()` for regeneration (counts against `max_iterations`). All the
  data Phase 7 needs is produced here.
- **Phase 8/9 (Validation/Tests in Docker):** run against the already-patched workspace.

---

## Out of Scope (explicit)

- The conditional retry edge `apply_patches → developer` on patch failure — **Phase 7**.
- Changing `DeveloperAgent.develop()` to consume `PatchResult` feedback — **Phase 7**.
- Git branch/commit/push — **Phase 5**.
- Any real PR creation — **Phase 6**.
- Docker isolation, real linters, real test runners — **Phases 8–10**.

In this phase, `apply_patches` always proceeds to `validator`, regardless of patch outcome.
The outcome is recorded in `patch_results` and surfaced; acting on it is the next phase.

---

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| LLM diff has wrong `@@` line numbers / context, `git apply` rejects it | Medium | Phase 3 full-file context makes diffs accurate; `--3way` absorbs small shifts; clean failure → Phase 7 regeneration. Never silently swallowed. |
| LLM emits diff without `a/`…`b/` prefixes or with markdown fences | Medium | Developer prompt already specifies `--- a/…`/`+++ b/…` format; on reject, record `error` + `failed_patch` so the failure is visible and Phase 7 can re-prompt. (Optional hardening: strip stray fences before apply.) |
| Re-applying on a retry iteration fails because the change is already present | Certain without mitigation | `apply_patches` calls `rollback_all` at node start, applying each iteration's diffs against a pristine tree. |
| Patch targets a path outside the workspace (traversal) | Low | Normalize and verify the resolved path is within `workspace_path`; otherwise return a failed `PatchResult` with no write. |
| `git` binary absent on host | Low | Already required by Phase 2's clone; document as a host prerequisite. Surfaces as a clear subprocess error, not a silent failure. |
| `git apply --3way` succeeds but produces a semantically wrong merge | Low | Validator/Reviewer (LLM) still run downstream on the result; Phase 7 loop catches review rejection. |
| Workspace is not a git repo (e.g. future non-clone source) | Low | Phase 2 always clones with git, so `.git` is present; `rollback_all`/`git apply` assume it. Documented as a Phase 2 invariant. |