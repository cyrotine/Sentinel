# Spec: Git Operations

## Overview

The Git Operations service turns the patched workspace into a **real, pushed branch** on
GitHub. Until this phase, Phase 4 applies the Developer's diffs to files on disk inside the
per-run workspace, but those modifications live only on the host's filesystem on the
default branch of a shallow clone — they are never committed, never branched, never pushed.
This phase takes the applied changes and: creates a feature branch, configures a bot commit
identity, stages exactly the files that were successfully patched, commits with a structured
message, and pushes the branch to the remote using the user's PAT.

**Why it exists.** The critical path to a real pull request is
`workspace → patch → git → PR`. Phase 2 cloned the repo, Phase 3 gave the Developer full
files, Phase 4 made the diffs real on disk. This phase is the bridge between "files changed
locally" and "a branch exists on GitHub that a PR can be opened against." Without a pushed
branch, Phase 6 (`GitHubPRService`) has no head ref to open a pull request from.

**How it contributes to autonomous engineering.** Committing and pushing is the second half
of the "Act" step (Think → Decide → **Act**). It is also the first phase that performs a
**write operation against the user's GitHub account**, so it is where the locked PAT
architecture (encrypted at rest, never logged, never sent to the frontend, `repo` scope)
first does real work. The pushed branch + commit SHA become the ground-truth handoff that
Phase 6 consumes.

---

## Depends On

- **Phase 2 — Repository Workspace** (`07-repository-workspace`): `state.workspace_path`
  points at a cloned git repo whose `origin` is the target GitHub repository.
  `WorkspaceManager._authenticated_url` is the PAT-injection precedent this phase reuses for
  push.
- **Phase 4 — Patch Executor** (`09-patch-executor`): `state.patch_results` is the
  authoritative list of which files were actually modified on disk. Git stages exactly the
  files where `PatchResult.applied is True`. With nothing applied, there is nothing to commit.

This phase produces the pushed-branch + commit-SHA signal that **Phase 6 — GitHub PR
Creation** consumes. It does **not** depend on Phase 6 or Phase 7; it ships and is testable
on its own (verify the branch exists on the remote).

---

## User Story

As a repository owner, I want Forge to commit its applied code changes onto a fresh feature
branch and push that branch to my GitHub repository using my PAT — staging only the files it
actually changed and committing with a message that links the originating issue — so that a
reviewable branch exists on GitHub and the downstream PR can be opened against it without any
manual git work on my part.

---

## Architectural Decision (resolved)

**Git runs in `BrainService` *after* the graph completes — it is NOT a LangGraph node.**

Phase 4 deliberately placed `PatchExecutor` in `packages/agents/` so it could run *as a graph
node* (`apply_patches`), because the Phase 7 auto-repair loop must be able to route a failed
patch back to the Developer. **Git operations are the opposite case** and the location
decision is inverted:

1. **The PAT must never enter graph state.** `SentinelState` is streamed, accumulated, and
   partially persisted into `AgentRun.result`. CLAUDE.md is explicit: the PAT is *never*
   logged and *never* leaves the backend. A push needs the PAT and the authenticated remote
   URL; putting either on `SentinelState` would leak a secret into streamed/persisted state.
   Therefore push must run at the **application layer**, which already holds the decrypted
   `repo.github_pat`, not inside an app-agnostic graph node.
2. **`BrainService` already owns the workspace lifecycle** (clone before the graph, cleanup
   in `finally`). Committing and pushing the post-graph workspace state is a natural
   extension of that ownership.
3. **Git is terminal, not iterative.** Unlike patch application, there is no need to re-enter
   git mid-pipeline; it runs once, after the Reviewer/PR-Generator have produced their
   verdict and the branch name.

Therefore `GitService` lives at **`apps/api/app/services/git_service.py`** (exactly where the
roadmap names it), is a pure git utility (GitPython, no DB, explicit args), and is invoked by
`BrainService` after the graph's `astream` loop completes. This honors the roadmap path and
the PAT security rule simultaneously.

> Consequence: Phase 5 adds **no graph node and no edge**. The graph topology is unchanged.

### Branch-name decision (resolved)

The roadmap names the branch `forge/issue-{number}-{slug}`. The existing `PRGeneratorAgent`
already emits a deterministic branch on `PullRequestDraft.branch`
(`{type}/issue-{number}-{slug}`, e.g. `fix/issue-5-button-label`). To keep **one source of
truth** and guarantee the pushed branch is identical to the branch the Phase 6 PR is opened
from, `GitService` derives its branch from `state.pull_request_draft.branch`.

**Uniqueness suffix (required by the no-force-push rule).** CLAUDE.md forbids force pushes
and branch deletion. A deterministic, issue-derived branch name collides on the remote when
the same issue is re-run, which would force a non-fast-forward push. To stay within the
no-force-push rule, `GitService` appends a short, run-unique suffix derived from
`agent_run_id` (first 8 hex chars), producing e.g.
`fix/issue-5-button-label-a1b2c3d4`. The **actually-pushed** branch is recorded on
`GitResult.branch`, which becomes the authoritative head ref for Phase 6 (it overrides the
draft's proposed branch). This is the same precedent as Phase 4 superseding the roadmap's
stated executor path — confirmed as the safe default; flag for the owner if a strict
`forge/`-prefixed, suffix-free name is desired instead (which would require accepting
re-run branch collisions or a delete-before-push, both disallowed today).

---

## Agent Changes

### Create

**`GitService`** — `apps/api/app/services/git_service.py`

A deterministic git utility (not LLM-powered). Operates on the already-patched workspace.

Responsibilities:
- Configure a repo-local bot commit identity (`user.name` / `user.email`) so commits succeed
  without relying on host git config.
- Create and check out a new feature branch.
- Stage exactly the files passed in (the applied-patch file list), not `git add -A`.
- Commit with a structured message that links the originating issue.
- Push the branch to the remote over HTTPS using a PAT-authenticated URL (mirrors
  `WorkspaceManager._authenticated_url`), never logging the authenticated URL.
- Return a typed `GitResult`; never raise on an expected git failure (e.g. nothing staged,
  push rejected) — report it. Reserve raised exceptions for genuinely broken inputs.

```python
class GitService:
    def commit_and_push(
        self,
        *,
        workspace_path: str,
        branch_name: str,
        commit_message: str,
        files: list[str],
        github_url: str,
        pat: str | None,
    ) -> GitResult: ...

    # Lower-level steps (composed by commit_and_push):
    def create_branch(self, workspace_path: str, branch_name: str) -> None: ...
    def commit_changes(self, workspace_path: str, message: str, files: list[str]) -> str: ...
    def push_branch(self, workspace_path: str, github_url: str, pat: str | None, branch_name: str) -> None: ...
```

Instantiate once as a module-level singleton: `git_service = GitService()`.

**Mechanism.** Use **GitPython** (already a dependency via Phase 2's `WorkspaceManager`),
operating on `git.Repo(workspace_path)`:
- Branch: `repo.git.checkout("-b", branch_name)`.
- Identity: `repo.git.config("user.name", …)` / `repo.git.config("user.email", …)` at
  repo-local scope (a noreply bot identity, e.g. `Forge Bot` /
  `forge-bot@users.noreply.github.com`).
- Stage: `repo.index.add(files)` (paths relative to repo root, taken from
  `PatchResult.file_path`).
- Commit: `repo.index.commit(message)`; capture the resulting SHA.
- Push: build the authenticated URL with the PAT and push an explicit refspec
  `repo.git.push(authenticated_url, f"{branch_name}:{branch_name}")` — pushing to a fresh,
  uniquely-named remote branch (fast-forward only; **no `--force`**).

This is git plumbing on static text files, **not** code execution — the deferred Docker
sandbox rule does not apply.

### Modify

No existing agent is modified. `PRGeneratorAgent` already produces `PullRequestDraft.branch`
and `.base_branch`; Phase 5 consumes them and does not change its signature. (Optionally,
`PRGeneratorAgent`'s `forge/` prefix alignment is noted under *Out of Scope*.)

---

## Workflow Changes

**No graph nodes, no edges, no routing changes.** Per the resolved decision above, git runs
in `BrainService` after `graph.astream(...)` completes, so the LangGraph topology in
`graph.py` is untouched.

### Inputs (read by `BrainService` after the graph completes)

- `accumulator["patch_results"]` — `list[PatchResult]`; the applied files are
  `[r.file_path for r in patch_results if r.applied]`.
- `accumulator["pull_request_draft"]` — `PullRequestDraft`; supplies the proposed branch
  name and the commit-message inputs (issue number/title via `selected_issue`).
- `repo.github_url`, `repo.github_pat` — already fetched by `BrainService` for the Phase 2
  clone; retained in scope for the push.

### Outputs

- `git_result` — a `GitResult`, computed post-graph and merged into the persisted
  `AgentRun.result` (see *Database Changes*). Becomes the authoritative branch/SHA for
  Phase 6.

### State Changes

Add **one new model** to `packages/workflows/forge_workflows/state.py` and export it:

```python
class GitResult(BaseModel):
    """Outcome of committing and pushing the patched workspace to the remote.

    Produced by BrainService via GitService *after* the graph completes — it is
    intentionally NOT a SentinelState field, because the push requires the PAT,
    which must never enter streamed/persisted graph state.
    """

    branch: str = Field(..., description="The branch actually created and pushed (authoritative for Phase 6)")
    committed: bool = Field(..., description="Whether a commit was created")
    commit_sha: str | None = Field(default=None, description="SHA of the created commit, if any")
    pushed: bool = Field(..., description="Whether the branch was pushed to the remote")
    files_committed: list[str] = Field(
        default_factory=list, description="Repo-relative paths staged and committed"
    )
    error: str | None = Field(
        default=None, description="git failure reason when committed/pushed is False"
    )
```

> **`SentinelState` is intentionally NOT extended in this phase.** Git output does not flow
> through any graph node, and adding PAT-derived results into streamed state risks secret
> leakage. `GitResult` lives in the shared `state.py` schema module (typed contract, no raw
> dicts) but is produced and consumed only at the application layer. Phase 6 will add
> `pull_request_url` / `pull_request_number` to `SentinelState` per its own roadmap entry;
> that is Phase 6's call, not this phase's.

No new `SentinelStatus` value is required (no new node/stage). `BrainService` continues to
report `"running"` → `"completed"`; the git step happens between the stream completing and
the final `"completed"` write.

---

## Database Changes

No schema changes. No migration.

`git_result` is serialized into the existing JSON `AgentRun.result` blob alongside
`selected_issue`, `plan`, `code_changes`, `patch_results`, `review`, and
`pull_request_draft`. Because git runs **post-graph** (not in the accumulator stream),
`BrainService` adds it to the result dict explicitly rather than via `_RESULT_FIELDS`:

```python
result = {field: _dump(accumulator.get(field)) for field in _RESULT_FIELDS}
result["git_result"] = _dump(git_result)  # None if git was skipped
```

The PAT is **never** written to `result`, logs, or any response.

---

## Retrieval Changes

No Qdrant changes. `GitService` touches the filesystem and the GitHub remote only.

---

## API Changes

No new endpoints. No request/response schema changes.

`git_result` appears inside the already-serialized `result` JSON returned by the existing
agent-run detail endpoint — no new field on any response model, no contract change. (The
endpoint must continue to never expose `github_pat`; `GitResult` contains no secret.)

---

## Frontend Changes

None required for this phase.

Optional (defer to a UI pass): the agent-run detail view could render the pushed branch name
and commit SHA (and a link to the branch on GitHub) from `result.git_result`. Not in scope
here; listed only so it is not forgotten.

---

## Files To Modify

| File | Change |
|---|---|
| `packages/workflows/forge_workflows/state.py` | Add `GitResult` model; export it from `forge_workflows.state` (imported by `git_service.py` and `brain_service.py`). No `SentinelState` field added. |
| `apps/api/app/services/brain_service.py` | After the `astream` loop succeeds: derive applied-file list from `patch_results`; gate on (≥1 applied file **and** `pull_request_draft` present); build the structured commit message from `selected_issue` + `pull_request_draft`; resolve a run-unique branch name; call `git_service.commit_and_push(...)` via `asyncio.to_thread`; store `git_result`; add `result["git_result"] = _dump(git_result)`. Retain `repo.github_url` / `repo.github_pat` in scope for the push. Git failures must not fail the whole run — log and record `GitResult.error`. |

---

## Files To Create

| File | Purpose |
|---|---|
| `apps/api/app/services/git_service.py` | `GitService` class + `git_service` singleton — configures bot identity, creates the feature branch, stages the applied files, commits with a structured issue-linking message, and pushes via a PAT-authenticated remote URL. Returns `GitResult`; never logs the authenticated URL or PAT. |

---

## New Packages

No new packages. GitPython is already a dependency (Phase 2 `WorkspaceManager`). `hashlib`/
string slicing for the branch suffix, `asyncio`, and `pathlib` are stdlib. `GitResult` reuses
Pydantic (already a dependency).

---

## Implementation Rules

- All new models are Pydantic `BaseModel` subclasses; no raw dicts between layers.
- `GitService` is a **pure** git utility — no LLM, no database, no HTTP framework, no
  `app.*` model imports. It may import `GitResult` from `forge_workflows.state`.
- **PAT handling:** never log the PAT or the authenticated remote URL; redact on any error.
  Mirror `WorkspaceManager._authenticated_url` for the `x-access-token:{pat}@host` form. The
  PAT never touches `SentinelState`, `AgentRun.result`, or any API response.
- **No force pushes, no branch deletion** (CLAUDE.md). Guarantee a fresh remote branch via
  the run-unique suffix; push fast-forward only. Never pass `--force`/`--force-with-lease`.
- Stage **only** the files in the applied-patch list (`PatchResult.applied is True`); never
  `git add -A` (avoids committing stray untracked artifacts).
- `GitService` must **never silently swallow a git failure**: a push rejection or empty
  staging area returns a `GitResult` with `committed`/`pushed` set accurately and `error`
  populated. The agent run is still marked `completed`; the git outcome is surfaced in
  `result.git_result`.
- All filesystem/git work targets `workspace_path` only (paths from `PatchResult.file_path`
  are repo-relative and were already traversal-guarded by Phase 4).
- GitPython is synchronous; `BrainService` wraps the `git_service` call in
  `asyncio.to_thread` (same reasoning as `WorkspaceManager.clone`).
- No Docker sandbox for this phase — committing/pushing static files is not code execution
  (per the CLAUDE.md HTML-phase carve-out).
- Type-checks cleanly (`mypy`/`pyright`): typed `list[str]`, `GitResult` return, no stray
  `Any`.

---

## Definition Of Done

- [ ] `GitResult` model exists in `state.py` with `branch`, `committed`, `commit_sha`, `pushed`, `files_committed`, `error`, and is exported from `forge_workflows.state`.
- [ ] `GitService` exists at `apps/api/app/services/git_service.py` with a `git_service` singleton.
- [ ] `create_branch()` creates and checks out the feature branch in the workspace.
- [ ] `commit_changes()` sets a repo-local bot identity, stages exactly the supplied files, commits, and returns the commit SHA.
- [ ] `push_branch()` pushes the branch to `origin` via a PAT-authenticated URL without logging the URL or PAT, fast-forward only (no `--force`).
- [ ] `commit_and_push()` composes the steps and returns a populated `GitResult`.
- [ ] The pushed branch name is run-unique (issue-derived name + `agent_run_id` short suffix); `GitResult.branch` records the actual pushed branch.
- [ ] On an empty applied-file list, `BrainService` skips git and persists `git_result = None` (no empty commit, no raise).
- [ ] A git/push failure returns a `GitResult` with `error` set and does **not** fail the agent run (run still completes; failure surfaced in `result.git_result`).
- [ ] `BrainService` builds the commit message from the selected issue (`type: resolve issue #N - title` + body referencing `Resolves #N`).
- [ ] `git_service` is called via `asyncio.to_thread`; the event loop is not blocked.
- [ ] The PAT never appears in logs, `AgentRun.result`, or any API response.
- [ ] No graph node, edge, or `SentinelStatus` value was added; `graph.py` is unchanged.
- [ ] End-to-end on a static HTML repo: after a run, the feature branch exists on the GitHub remote, contains exactly the patched file(s), and `GitResult` reports `committed=True, pushed=True` with a real SHA.
- [ ] Type-checking passes with no new errors.

---

## Architecture Impact

**Affected systems:**
- `apps/api` services: new `GitService` (peer of `WorkspaceManager`); `BrainService` gains a
  post-graph commit/push step and one extra `result` field.
- `forge_workflows.state`: new `GitResult` schema (application-layer contract; not on
  `SentinelState`).
- `graph.py` / `forge_agents`: **unchanged**.

**Dependencies introduced:**
- A runtime dependency on the GitHub remote being reachable and the PAT having `repo` scope
  for push. The PAT and remote URL already exist (Phase 2 clone). No new Python package.
- `git_service.py` → `forge_workflows.state` (same one-way direction `brain_service.py`
  already uses).

**Scalability concerns:**
- One commit + one push per run. Trivial for the HTML MVP. Push latency is network-bound;
  wrapped in `asyncio.to_thread` so it never blocks the event loop.
- Shallow clone (`depth=1`) push: GitHub accepts pushes of new commits from shallow clones;
  no `--unshallow` needed for the target profile.

**Future extensions:**
- **Phase 6 (GitHub PR):** `GitHubPRService` opens a PR with head = `GitResult.branch`,
  base = `pull_request_draft.base_branch` (or `repo.default_branch`), title/body from the
  draft. `GitResult` is the authoritative head ref.
- **Phase 7 (Auto Repair Loop):** unaffected — it loops *inside* the graph (developer ↔
  validator/reviewer); git runs only once after the loop settles, so the final pushed branch
  reflects the last accepted iteration.

---

## Out of Scope (explicit)

- Real PR creation against the GitHub API — **Phase 6**.
- Adding `pull_request_url` / `pull_request_number` to `SentinelState` — **Phase 6**.
- Aligning `PRGeneratorAgent`'s branch prefix to a strict `forge/` (a one-line change in
  `pr_generator.py`); Phase 5 consumes whatever `PullRequestDraft.branch` provides and only
  appends the uniqueness suffix.
- Any graph node / edge changes, conditional routing, or new `SentinelStatus` value.
- Force-push / branch-overwrite / branch-deletion strategies (forbidden by CLAUDE.md).
- Docker isolation, real linters, real test runners — **Phases 8–10**.

---

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| PAT leaks via logs or persisted state | High impact / Low likelihood | Never log the authenticated URL or PAT; redact on error; git runs at app layer so PAT never enters `SentinelState`/`AgentRun.result`; `GitResult` carries no secret. |
| Deterministic branch name collides on re-run → forced non-fast-forward push | Certain without mitigation | Append `agent_run_id` short suffix for a fresh remote branch every run; push fast-forward only; never `--force`. |
| Commit fails because host git has no `user.name`/`user.email` | Medium | `GitService` sets a repo-local bot identity before committing; does not rely on host config. |
| Push rejected (auth/scope/branch protection) | Medium | PAT requires `repo` scope (locked decision); on rejection, return `GitResult(pushed=False, error=…)` and complete the run without failing — surfaced for the user, retriable. |
| Nothing applied (all patches failed in Phase 4) → empty commit | Medium | Gate on a non-empty applied-file list; skip git entirely and persist `git_result = None`. |
| Pushing from a shallow (`depth=1`) clone fails | Low | GitHub supports pushing new commits from shallow clones; the target profile needs no history. Document as a Phase 2 invariant; surfaces as a clear push error if ever violated. |
| Staged file path mismatch (relative vs absolute) | Low | Stage using `PatchResult.file_path` (already repo-relative, traversal-guarded by Phase 4) via `repo.index.add`. |
| Branch name from draft is empty/invalid | Low | Fall back to a deterministic `forge/issue-{number}-{run_short}` when `pull_request_draft.branch` is blank; sanitize to a valid git ref. |