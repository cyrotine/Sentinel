# Spec: Repository Workspace

## Overview

Every downstream phase (full file retrieval, patch execution, git operations, PR creation) requires agents to operate on real files from a real clone of the target repository. Currently the pipeline runs entirely on vector-store chunks — it has no filesystem representation of the repository.

This feature introduces `WorkspaceManager`, a service that clones a repository to a temporary directory on the API host before the LangGraph pipeline executes, stores the workspace path in `SentinelState` so all agents can read from it, and cleans up after the run completes (success or failure).

It also introduces `github_pat` storage on the `Repository` model so Forge has the credentials needed to clone private repositories and, in later phases, push branches and create pull requests.

This is the foundation everything else depends on. Phases 3–7 cannot be implemented without it.

---

## Depends On

No unimplemented phases. Phases 1 through the current pipeline are complete.

---

## User Story

As a developer using Forge, I want to provide my GitHub Personal Access Token when connecting a repository so that Forge can clone it and operate on real files rather than vector-store excerpts.

---

## Agent Changes

No new agents.

### Modify

**`DeveloperAgent`** — no code changes in this phase, but after Phase 2 the `workspace_path` field is available in `SentinelState` for Phase 3 to pass full file contents.

---

## Workflow Changes

### State Changes

Add one field to `SentinelState` in `packages/workflows/forge_workflows/state.py`:

```python
# --- Infrastructure (set by BrainService before the graph runs) ---
workspace_path: str | None = Field(
    default=None,
    description="Absolute path to the cloned repository on the API host filesystem",
)
```

No new graph nodes or edges in this phase. The workspace is cloned **before** the graph starts and cleaned up **after** it finishes — this is orchestration logic in `BrainService`, not a LangGraph node.

### Inputs / Outputs

No changes to graph inputs or outputs. `workspace_path` is populated by `BrainService` before `graph.astream()` is called.

---

## Database Changes

### Modify: `repositories` table

Add column `github_pat` — encrypted storage of the user's Personal Access Token.

```sql
ALTER TABLE repositories ADD COLUMN github_pat TEXT DEFAULT NULL;
```

**Security note:** For the MVP this is stored as plaintext. The column must never be returned in any API response. Encryption at rest is a follow-up task once the MVP is validated.

Migration file: `apps/api/alembic/versions/003_add_github_pat_to_repositories.py`

---

## Retrieval Changes

No retrieval changes.

---

## API Changes

### Modified: `POST /api/repositories`

Add optional `github_pat` to the request body.

**Request schema** (updated `RepositoryCreate`):
```json
{
  "github_url": "https://github.com/owner/repo",
  "github_pat": "ghp_xxxx"
}
```
`github_pat` is optional (nullable). Existing callers that omit it continue to work.

**Response schema:** unchanged (`RepositoryCreatedOut`).

No new endpoints. A user who wants to update their PAT on an existing repository must delete and re-register for the MVP.

---

## Frontend Changes

### Modified: `connect-repository-modal.tsx`

Add a second optional input field for the GitHub PAT below the URL field.

```
GitHub Repository URL  [required]
GitHub Personal Access Token  [optional — needed for private repos and PR creation]
```

- Field type: `password` (masked input so the token is not visible on screen).
- Placeholder: `ghp_xxxx (optional — required for write access)`
- The value is sent to `POST /api/repositories` in the request body as `github_pat`.

### Modified: `api.ts`

Update `registerRepository()` to accept an optional `pat` parameter:

```typescript
export async function registerRepository(
  githubUrl: string,
  pat?: string
): Promise<RepositoryCreatedOut> {
  return apiFetch<RepositoryCreatedOut>("/repositories", {
    method: "POST",
    body: JSON.stringify({ github_url: githubUrl, github_pat: pat || undefined }),
  })
}
```

---

## Files To Modify

| File | Change |
|------|--------|
| `packages/workflows/forge_workflows/state.py` | Add `workspace_path: str \| None` to `SentinelState` |
| `apps/api/app/models/repository.py` | Add `github_pat: Mapped[str \| None]` column |
| `apps/api/app/repositories/repository_repo.py` | Accept and store `github_pat` in `create()`; add `update_pat()` function |
| `apps/api/app/schemas/repository.py` | Add `github_pat: str \| None = None` to `RepositoryCreate` |
| `apps/api/app/api/repositories.py` | Pass `github_pat` through to `repository_service.get_or_create_repository()` |
| `apps/api/app/services/repository_service.py` | Accept and persist `github_pat` in `get_or_create_repository()` |
| `apps/api/app/services/brain_service.py` | Clone workspace before graph run; set `workspace_path` on state; cleanup in finally block |
| `apps/web/src/components/repositories/connect-repository-modal.tsx` | Add optional PAT password field |
| `apps/web/src/lib/api.ts` | Update `registerRepository()` signature to accept optional PAT |

---

## Files To Create

| File | Purpose |
|------|---------|
| `apps/api/app/services/workspace_manager.py` | `WorkspaceManager` class — clone, path resolution, cleanup |
| `apps/api/alembic/versions/003_add_github_pat_to_repositories.py` | Migration to add `github_pat` column |

---

## New Packages

No new packages. `gitpython` is already declared in `apps/api/pyproject.toml` and is used by `IngestionService`. `shutil` and `asyncio` are stdlib.

---

## Implementation Rules

### `WorkspaceManager`

```python
# apps/api/app/services/workspace_manager.py

class WorkspaceManager:
    def __init__(self, base_dir: str) -> None:
        self._base_dir = Path(base_dir)

    def workspace_path(self, run_id: str) -> Path:
        return self._base_dir / run_id

    async def clone(self, run_id: str, github_url: str, pat: str | None) -> str:
        """Clone repo to an isolated workspace. Returns the workspace path."""
        workspace = self.workspace_path(run_id)
        workspace.mkdir(parents=True, exist_ok=True)
        clone_url = self._authenticated_url(github_url, pat)
        # GitPython is synchronous — run in thread pool to avoid blocking event loop
        await asyncio.to_thread(
            git.Repo.clone_from, clone_url, str(workspace), depth=1
        )
        return str(workspace)

    def cleanup(self, run_id: str) -> None:
        shutil.rmtree(self.workspace_path(run_id), ignore_errors=True)

    @staticmethod
    def _authenticated_url(github_url: str, pat: str | None) -> str:
        """Inject PAT into HTTPS URL. Follows the same pattern as IngestionService._clone_url()."""
        parsed = urlparse(github_url.rstrip("/"))
        path = parsed.path.rstrip("/")
        if not path.endswith(".git"):
            path += ".git"
        if pat:
            return f"https://x-access-token:{pat}@{parsed.netloc}{path}"
        return f"https://{parsed.netloc}{path}"
```

Rules:
- Use `depth=1` (shallow clone) — the MVP targets tiny HTML repos; full history is unnecessary.
- `git.Repo.clone_from` runs via `asyncio.to_thread` — never block the async event loop.
- Follow the `x-access-token:{pat}@github.com` URL format — same as `IngestionService._clone_url()`.
- Cleanup always runs in a `finally` block in `BrainService`, even if the graph fails.
- Module-level singleton: `workspace_manager = WorkspaceManager(settings.clone_base_dir)`.

### `BrainService` integration

```python
async def start(self, run_id: uuid.UUID) -> None:
    workspace_path: str | None = None
    async with AsyncSessionLocal() as session:
        try:
            run = await agent_run_repo.get_by_id(session, run_id)
            repo = await repository_repo.get_by_id(session, run.repository_id)
            # ...existing status update...

            # Clone workspace (always attempt; PAT=None works for public repos)
            workspace_path = await workspace_manager.clone(
                str(run_id), repo.github_url, repo.github_pat
            )

            # ...existing inputs load and graph build...
            state = SentinelState(
                ...,
                workspace_path=workspace_path,
            )
            # ...existing graph.astream() loop...

        except Exception as exc:
            # ...existing error handling...
        finally:
            if workspace_path:
                workspace_manager.cleanup(str(run_id))
```

### PAT security

- `github_pat` must **never** appear in any `RepositoryOut` or other API response schema.
- `github_pat` must **never** be logged (use `logger.info("Cloning %s", repo.github_url)` — no token in the message).
- `RepositoryCreate.github_pat` must be `exclude=True` from any serialized output.

---

## Definition Of Done

- [ ] `github_pat` column exists in the `repositories` table (migration applied)
- [ ] `POST /api/repositories` accepts optional `github_pat` in request body
- [ ] `github_pat` is stored on the `Repository` model and never returned in API responses
- [ ] `WorkspaceManager.clone()` successfully clones a small public GitHub repository to `/tmp/forge_clones/{run_id}/`
- [ ] `WorkspaceManager.cleanup()` removes the workspace directory after the run
- [ ] Cleanup runs in a `finally` block — verified by triggering a graph failure and confirming the directory is removed
- [ ] `SentinelState.workspace_path` contains the cloned path during a successful agent run
- [ ] `SentinelState.workspace_path` is `None` when cloning is skipped
- [ ] `connect-repository-modal.tsx` has a masked PAT input field
- [ ] Submitting the connect form with a PAT stores it in the database
- [ ] `tsc --noEmit` passes with no errors

---

## Architecture Impact

**Affected systems:**
- `apps/api/app/services/` — new `WorkspaceManager`, modified `BrainService`
- `apps/api/app/models/` — `Repository` model gains `github_pat`
- `packages/workflows/forge_workflows/state.py` — `SentinelState` gains `workspace_path`
- `apps/web/` — connect modal gains PAT field

**Dependencies introduced:**
- None (GitPython already installed)

**Scalability concerns:**
- Each agent run creates a directory under `clone_base_dir`. Cleanup is synchronous and always runs. If the API process is killed before cleanup, orphaned directories accumulate. A startup sweep that removes directories older than N hours is a future hardening task.
- `depth=1` shallow clones keep disk usage minimal for the HTML MVP target.

**Future extensions:**
- Phase 3 (FileLoader) reads full file contents from `workspace_path`.
- Phase 4 (PatchExecutor) writes modified files to `workspace_path`.
- Phase 5 (GitService) creates a branch and commits changes inside `workspace_path`.
- Phase 6 (GitHubPRService) pushes the branch using the stored PAT.

---

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| PAT stored as plaintext in Postgres | Accepted for MVP | Add column-level encryption (e.g. `pgcrypto`) before production deployment |
| Clone fails due to network timeout | Low for MVP | `git.Repo.clone_from` raises `git.GitCommandError`; catch in `BrainService` and mark run as failed with descriptive error |
| PAT accidentally leaked in logs | Medium | Audit all log statements in `WorkspaceManager` and `BrainService` — never log the PAT string |
| Orphaned workspace directories if API crashes mid-run | Low for MVP | Acceptable; add startup cleanup sweep before public launch |
| Shallow clone missing files needed for context | Very low for MVP HTML repos | `depth=1` fetches the full working tree at HEAD; all files are present. Only commit history is truncated |
