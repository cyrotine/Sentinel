# Spec: GitHub Pull Request Creation

## Overview

Phase 6 closes the final gap between "Forge generates a PR draft" and "Forge opens a real
pull request on GitHub." After the `PRGeneratorAgent` produces a `PullRequestDraft` (title,
body, branch, base branch) and Phase 5 (`GitService`) commits and pushes that branch to the
remote, a new `GitHubPRService` calls the GitHub REST API to create the pull request using
the user's PAT.

The result — a real PR URL and number — is persisted in `AgentRun.result` and surfaced in
the run-detail UI as a clickable link.

**Why it exists.** The pipeline is not autonomous until it produces something a human can
act on without touching the terminal. A PR draft sitting in a database is a dead artefact;
a real GitHub PR is a live, reviewable, mergeable artifact. This phase is the final "Act"
step of the critical path:

```
clone → patch → commit+push → open PR
```

**How it contributes to autonomous engineering.** Opening a pull request is the highest-value
write operation Forge performs: it creates a permanent record, triggers CI, assigns reviewers,
and puts the work directly in front of the team. Every preceding phase exists to make this
step correct.

---

## Depends On

- **Phase 2 — Repository Workspace** (`07-repository-workspace`): workspace clone + `repo.github_pat`
- **Phase 4 — Patch Executor** (`09-patch-executor`): `patch_results` with applied file paths
- **Phase 5 — Git Operations** (`10-git-operations`): `git_result.branch` (the pushed branch name)
  and `git_result.pushed == True` (the branch must exist on the remote before a PR can be opened)
- **PR Generator Agent** (existing): `pull_request_draft.title`, `.body`, `.base_branch`

---

## User Story

As a repository owner, after watching Forge analyze my issue, write code, and push a branch,
I want Forge to automatically open a pull request on GitHub so that I receive a real,
reviewable PR — with title, description, and all context — without touching the terminal.

---

## Agent Changes

### Create

No new agent class. PR creation is a deterministic service call against a known REST API;
there is no LLM reasoning involved.

### Modify

No existing agents modified.

---

## Workflow Changes

The LangGraph graph itself does **not** change. The PR creation step runs **after the graph
completes**, in `BrainService`, alongside the existing `_run_git` step. This mirrors the
architectural decision from Phase 5: PAT-authenticated write operations stay outside the
graph so the PAT never enters streamed or persisted `SentinelState`.

### New post-graph step in BrainService

After `_run_git` returns a `GitResult`, `BrainService.start()` calls the new
`_run_github_pr` helper.

**Guard conditions** (skip PR creation if any are true):
- `git_result` is `None` — no git step ran
- `git_result.pushed is False` — branch was not pushed; no head ref exists on GitHub
- `pull_request_draft` is `None` — no PR metadata to use
- `repo.github_pat` is `None` — no PAT; cannot authenticate write operations

**On success**: store `pull_request_url` (str) and `pull_request_number` (int) in `result`.

**On failure**: log the error and store `pull_request_url = None`, `pull_request_number = None`.
Never let a PR creation error fail the overall `AgentRun` — the pushed branch and draft
remain available even when the API call fails.

### Inputs

- `git_result.branch` — the actual branch name pushed (authoritative; may differ from `draft.branch` due to slug sanitization)
- `pull_request_draft.title`, `.body`, `.base_branch` — PR metadata from the graph
- `repo.owner`, `repo.name`, `repo.github_pat` — repository identity + write credentials

### Outputs

Two new fields added to `AgentRun.result` (stored in the `agent_runs.result` JSONB column):

```python
pull_request_url: str | None    # e.g. "https://github.com/owner/repo/pull/42"
pull_request_number: int | None  # e.g. 42
```

### State Changes

`SentinelState` is **not modified**. The PAT must not enter graph state. The PR URL and
number are post-graph outputs stored directly in `AgentRun.result` by `BrainService`.

### Graph Nodes

No new graph nodes.

### Graph Edges

No graph edge changes.

---

## Database Changes

No new tables or columns. `AgentRun.result` is a `JSONB` column that already stores
arbitrary result data; the two new fields are written into that dict by `BrainService`.

The `repositories.github_pat` column was added in migration `003_add_github_pat_to_repositories`
(Phase 5). No additional migration is needed.

---

## Retrieval Changes

No retrieval changes.

---

## API Changes

### Modified: `AgentRunResult` schema

`apps/api/app/schemas/agent_run.py` — add two nullable fields:

```python
class AgentRunResult(BaseModel):
    selected_issue: dict | None = None
    plan: dict | None = None
    code_changes: list[dict] = []
    review: dict | None = None
    pull_request_draft: dict | None = None
    pull_request_url: str | None = None       # NEW
    pull_request_number: int | None = None    # NEW
```

These are read back from `agent_runs.result` JSONB by `AgentRunOut`.

No new endpoints. `GET /api/agent-runs/{run_id}` already returns the full `AgentRunOut`
including `result`.

---

## Frontend Changes

### Pages

No new pages.

### Components

**Modified: `apps/web/src/components/agents/agent-run-detail.tsx`**

After the existing "Pull request draft" section, add a "Pull request" section that renders
when `result.pull_request_url` is non-null:

```
┌────────────────────────────────────────────┐
│ PULL REQUEST                               │
│ ✓ Opened · PR #42                          │
│ → View on GitHub  (external link)          │
└────────────────────────────────────────────┘
```

- Green check icon + "Opened · PR #{number}" label
- Clickable link that opens `pull_request_url` in a new tab (`target="_blank" rel="noopener noreferrer"`)
- The existing "Pull request draft" section (title + body + branch) stays — both sections
  are shown when the PR was opened; draft only when the branch was not pushed or API failed

**Modified: `apps/web/src/lib/api.ts`**

Update `AgentRunResult` interface:

```typescript
export interface AgentRunResult {
  selected_issue: Record<string, unknown> | null
  plan: Record<string, unknown> | null
  code_changes: Record<string, unknown>[]
  review: Record<string, unknown> | null
  pull_request_draft: Record<string, unknown> | null
  pull_request_url: string | null     // NEW
  pull_request_number: number | null  // NEW
}
```

### Visualizations

No new visualizations.

### Dashboard Modules

No dashboard changes.

### State Management

Local `useState` only. No global state library introduced.

---

## Files To Modify

```
packages/github/forge_github/client.py
    create_pull_request() return type: str → tuple[str, int]
    Return both html_url and number from the GitHub API response.

apps/api/app/services/brain_service.py
    Import GitHubPRService.
    Add _run_github_pr() helper method.
    Call _run_github_pr() after _run_git() in start().
    Write pull_request_url and pull_request_number into result dict.

apps/api/app/schemas/agent_run.py
    AgentRunResult: add pull_request_url and pull_request_number fields.

apps/web/src/lib/api.ts
    AgentRunResult interface: add pull_request_url and pull_request_number.

apps/web/src/components/agents/agent-run-detail.tsx
    Add "Pull request" section rendering the live PR link.
```

---

## Files To Create

```
apps/api/app/services/github_pr_service.py
    GitHubPRService — thin wrapper around GitHubClient.create_pull_request().
    Handles owner/name parsing from repo.full_name.
    Module-level singleton: github_pr_service.
```

---

## New Packages

No new packages. `forge_github.client.GitHubClient` (already in `packages/github/`) and
`httpx` (already a dependency) provide everything needed.

---

## Implementation Notes

### `GitHubPRService` contract

```python
class GitHubPRService:
    async def create_pull_request(
        self,
        *,
        full_name: str,     # "owner/repo" from Repository.full_name
        pat: str,
        title: str,
        body: str,
        head: str,          # the pushed branch name from GitResult.branch
        base: str,          # target branch, e.g. "main"
    ) -> tuple[str, int]:
        """Open a real GitHub PR. Returns (html_url, pr_number)."""
```

Parse `owner, name = full_name.split("/", 1)` inside the service — callers pass the
single `full_name` string, not separate owner/name.

### `BrainService._run_github_pr` contract

```python
async def _run_github_pr(
    self,
    *,
    repo_full_name: str,
    repo_github_pat: str | None,
    git_result: GitResult | None,
    accumulator: dict[str, Any],
) -> tuple[str | None, int | None]:
    """Returns (pull_request_url, pull_request_number) or (None, None) when skipped."""
```

Caller in `start()`:
```python
pr_url, pr_number = await self._run_github_pr(
    repo_full_name=repo.full_name,
    repo_github_pat=repo.github_pat,
    git_result=git_result,
    accumulator=accumulator,
)
result["pull_request_url"] = pr_url
result["pull_request_number"] = pr_number
```

### Branch name: use `git_result.branch`, not `draft.branch`

`PRGeneratorAgent` generates a branch slug from the issue title. `BrainService._run_git`
appends a 8-char run ID suffix and sanitizes for git compatibility. The name that was
_actually pushed_ is `git_result.branch`. Always use that as `head` in the PR creation
call — using `draft.branch` would reference a branch that does not exist on the remote.

### Failure isolation

`_run_github_pr` must never raise. Wrap the `GitHubPRService` call in `try/except`,
log the error at `WARNING` level, and return `(None, None)`. The run completes as
`"completed"` regardless — the pushed branch is the primary deliverable; the PR is a bonus
that requires a valid PAT and reachable GitHub API.

---

## Implementation Rules

- No business logic in API route handlers — PR creation lives in `BrainService`, not in a route
- TypeScript strict mode; no `any` without justification
- `pull_request_url` / `pull_request_number` are never computed in the graph — they are
  post-graph side effects managed by `BrainService`
- The PAT is never logged, never returned in API responses, never stored in `SentinelState`
- `GitHubPRService` is a pure async service — no database, no LLM, no filesystem access

---

## Definition Of Done

- [ ] `GitHubClient.create_pull_request` returns `tuple[str, int]` (url, number)
- [ ] `GitHubPRService` created; `github_pr_service` singleton exported
- [ ] `BrainService._run_github_pr` implemented with all guard conditions
- [ ] `_run_github_pr` called after `_run_git` in `BrainService.start()`
- [ ] `result["pull_request_url"]` and `result["pull_request_number"]` written to the result dict
- [ ] PR creation failure does not fail the `AgentRun` — run still completes as `"completed"`
- [ ] `AgentRunResult.pull_request_url` and `pull_request_number` fields added to backend schema
- [ ] `AgentRunResult` TS interface updated with both fields
- [ ] `agent-run-detail.tsx` shows "Pull request" section with live link when `pull_request_url` is set
- [ ] PR link opens in new tab with `rel="noopener noreferrer"`
- [ ] When PAT is missing or push failed, PR section is absent — draft section still shows
- [ ] `branch` passed to `GitHubPRService` is `git_result.branch` (the actual pushed name), not `draft.branch`

---

## Architecture Impact

**Affected systems:**
- `packages/github/forge_github/client.py` — return type change (non-breaking; only caller was internal)
- `apps/api/app/services/brain_service.py` — gains `_run_github_pr` post-graph step
- `apps/api/app/schemas/agent_run.py` — additive schema change (backward-compatible; new fields default to `None`)
- Frontend `AgentRunResult` interface — additive; existing code handles `null` fields

**Dependencies introduced:**
- None. All required infrastructure (GitHubClient, httpx, PAT storage, workspace clone) is
  already in place from Phases 2–5.

**Scalability concerns:**
- GitHub REST API rate limit: 5,000 requests/hour per PAT. PR creation is 1 request per run.
  Not a concern at current scale.
- The PR creation call is `await`-ed inside an `async with AsyncSessionLocal()` block.
  If the GitHub API is slow, the session stays open longer. Acceptable given the 30s httpx timeout
  already set on `GitHubClient`.

**Future extensions:**
- Phase 7 (Auto Repair Loop): when `review.approved is False`, route back to developer. After
  re-review passes, the PR already exists — a future enhancement could push additional commits
  to the same branch rather than opening a new PR.
- Labels, assignees, and reviewers could be added to the `create_pull_request` call using
  `GitHubClient` once the user can configure them.

---

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| PAT lacks `repo` scope — PR creation returns 403 | Medium | Log the error clearly; run completes; UI shows draft only. Document required PAT scope in connect modal tooltip. |
| Branch name on remote differs from `draft.branch` slug | Low | Always use `git_result.branch` (the name actually pushed), not `draft.branch` |
| PR already exists for the branch (duplicate run) | Low | GitHub returns 422 "A pull request already exists". Catch and log; treat as non-fatal; do not expose to UI as a failure |
| `git_result` is `None` (no patches applied, git step skipped) | Medium | Guard condition in `_run_github_pr`: skip when `git_result is None` or `not git_result.pushed` |
| GitHub API timeout (30s httpx default) | Low | `_run_github_pr` catches all exceptions; run still completes |
