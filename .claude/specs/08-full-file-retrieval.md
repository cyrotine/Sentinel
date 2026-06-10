# Spec: Full File Retrieval

## Overview

Full File Retrieval gives every downstream agent — specifically the Planner and Developer — access to complete file contents read directly from the cloned workspace on disk, alongside the Qdrant chunks that already exist.

**Why it exists.** The `DeveloperAgent` currently receives only Qdrant chunks: short snippets of relevant code that were indexed at ingestion time. When the LLM generates a unified diff it can only see those snippets, not the full file. This produces two failure modes:

1. The generated `@@ … @@` line numbers and context lines are wrong because the LLM guesses at what surrounds the snippet.
2. The patch fails to apply in Phase 4 because the context lines do not match what is actually in the file.

Full File Retrieval fixes this by adding a deterministic `load_full_files` node that reads complete file contents from the workspace immediately after context retrieval. The PlannerAgent and DeveloperAgent both receive these full files so they operate on the same ground-truth source as a human developer would.

**How it contributes to autonomous engineering.** Patches generated with full file context apply cleanly in Phase 4, which means Phase 5 (git commit) and Phase 6 (PR creation) can proceed without a repair loop. This is the last purely contextual phase before real file modification begins.

---

## Depends On

- **Phase 2 — Repository Workspace**: `workspace_path` must be set on `SentinelState` and the repository must be cloned before `load_full_files` runs. No workspace, no files to read.

---

## User Story

As a repository owner, I want Forge to generate accurate code patches by reading the complete content of every file it is about to modify, so that the produced unified diffs apply cleanly without a repair loop.

---

## Agent Changes

### Create

**`FileLoader`** — `packages/agents/forge_agents/file_loader.py`

A deterministic filesystem utility (not LLM-powered). Reads complete file contents from the cloned workspace.

Responsibilities:
- Accept a `workspace_path` and a list of relative `file_paths`.
- Read each file from `Path(workspace_path) / file_path`.
- Detect language from file extension.
- Return a list of `FullFileContext` objects.
- Skip files that do not exist in the workspace and log a warning.

```python
class FileLoader:
    def load_files(
        self,
        workspace_path: str,
        file_paths: list[str],
    ) -> list[FullFileContext]: ...
```

No `__init__` dependencies. Instantiate once as a module-level singleton: `file_loader = FileLoader()`.

### Modify

**`DeveloperAgent`** — `packages/agents/forge_agents/developer.py`

Update `develop()` signature to accept `full_file_contexts: list[FullFileContext]`.

Update `_build_prompt()` to include a `Full File Contents` block that shows the complete file for each path in `plan.affected_files`. When a full file is available, prefer it over the Qdrant chunk for the same path. Chunks remain useful for files that were not loaded (e.g. files not in the workspace).

Prompt change: replace the current `Current Code` section (chunks only) with two sections:
1. `Full File Contents` — complete files, formatted with file headers and line-numbered content.
2. `Additional Context (Qdrant Chunks)` — chunks for any files not covered by full file loading.

**`PlannerAgent`** — `packages/agents/forge_agents/planner.py`

Update `plan()` signature to accept `full_file_contexts: list[FullFileContext]`.

Update `_build_prompt()` to include full file content in the code context block, letting the Planner see exact line numbers and structure when choosing which files to change and how.

---

## Workflow Changes

### Inputs

- `state.workspace_path` — set by Phase 2's `BrainService` before the graph runs.
- `state.relevant_chunks` — file paths from Qdrant used to determine which files to load.

### Outputs

- `state.full_file_contexts` — `list[FullFileContext]` populated by `load_full_files`.

### State Changes

Add to `packages/workflows/forge_workflows/state.py`:

**New model:**

```python
class FullFileContext(BaseModel):
    file_path: str      # Relative path from repo root
    content: str        # Complete file contents
    language: str | None = None
    line_count: int = 0
```

**New field on `SentinelState`** (between the Phase 3 Retrieve block and Phase 4 Plan block):

```python
full_file_contexts: list[FullFileContext] = Field(
    default_factory=list,
    description="Complete file contents read from the workspace for files relevant to the selected issue",
)
```

**New `SentinelStatus` value:**

```python
LOADING_FILES = "loading_files"
```

### Graph Nodes

**New node: `load_full_files`**

Location: `packages/workflows/forge_workflows/graph.py`

```python
LOAD_FULL_FILES = "load_full_files"

async def load_full_files(state: SentinelState) -> dict:
    # Deduplicate file paths from relevant_chunks
    # Call file_loader.load_files(state.workspace_path, unique_paths)
    # Return {"full_file_contexts": [...], "status": SentinelStatus.LOADING_FILES, ...}
```

If `workspace_path` is `None` (e.g. running without Phase 2 in tests), log a warning and return an empty list — do not raise.

### Graph Edges

Replace the existing direct edge:

```
retrieve_context → planner
```

With:

```
retrieve_context → load_full_files → planner
```

Update `developer` and `planner` node closures to pass `state.full_file_contexts` to the respective agent methods.

---

## Database Changes

No database changes.

---

## Retrieval Changes

No Qdrant changes. `FileLoader` reads from the filesystem only. Qdrant chunks remain in use for relevance ranking — full files supplement them, they do not replace them.

---

## API Changes

No new endpoints. No changes to existing response schemas.

---

## Frontend Changes

None. This phase is entirely backend/pipeline.

---

## Files To Modify

| File | Change |
|---|---|
| `packages/workflows/forge_workflows/state.py` | Add `FullFileContext` model, `full_file_contexts` field on `SentinelState`, `LOADING_FILES` status on `SentinelStatus` |
| `packages/workflows/forge_workflows/graph.py` | Add `LOAD_FULL_FILES` constant, `load_full_files` node function, edge `retrieve_context → load_full_files → planner`, inject `full_file_contexts` into `planner` and `developer` node closures |
| `packages/agents/forge_agents/developer.py` | Add `full_file_contexts: list[FullFileContext]` param to `develop()` and `_build_prompt()`; restructure prompt to show full files first, then supplementary chunks |
| `packages/agents/forge_agents/planner.py` | Add `full_file_contexts: list[FullFileContext]` param to `plan()` and `_build_prompt()`; include full file content in code context block |

---

## Files To Create

| File | Purpose |
|---|---|
| `packages/agents/forge_agents/file_loader.py` | `FileLoader` class — reads complete file contents from the cloned workspace; detects language from extension; returns `list[FullFileContext]` |

---

## New Packages

No new packages. `pathlib` is stdlib. All other imports (`forge_workflows.state`) are already present.

---

## Implementation Rules

- TypeScript strict mode: N/A (backend-only phase).
- All new models must be Pydantic `BaseModel` subclasses.
- `FileLoader` must be a pure filesystem utility — no LLM, no database, no HTTP.
- `load_full_files` graph node must not raise on missing workspace; it degrades gracefully to an empty list.
- Full file content must NEVER be fetched via GitHub API — read from `workspace_path` only.
- Qdrant chunks remain in use alongside full files. Do not remove `relevant_chunks` from agent prompts.
- `FullFileContext` must be exported from `forge_workflows.state` (imported by `file_loader.py` and `graph.py`).
- The `LOAD_FULL_FILES` node name must be added to the node-name constants at the top of `graph.py`.
- Language detection: derive from file extension — `.py` → `"python"`, `.ts`/`.tsx` → `"typescript"`, `.js`/`.jsx` → `"javascript"`, `.html` → `"html"`, `.css` → `"css"`. Unknown extensions → `None`.

---

## Definition Of Done

- [ ] `FullFileContext` model exists in `state.py` with `file_path`, `content`, `language`, `line_count` fields.
- [ ] `SentinelState.full_file_contexts` field exists and defaults to `[]`.
- [ ] `SentinelStatus.LOADING_FILES` value exists.
- [ ] `FileLoader` class exists at `packages/agents/forge_agents/file_loader.py`.
- [ ] `FileLoader.load_files()` reads real file contents from `workspace_path / file_path`.
- [ ] `FileLoader.load_files()` skips missing files with a warning (does not raise).
- [ ] `FileLoader.load_files()` deduplicates file paths before reading.
- [ ] `FileLoader.load_files()` sets `line_count` to the actual number of lines in the file.
- [ ] `load_full_files` node exists in `graph.py` between `retrieve_context` and `planner`.
- [ ] `load_full_files` returns an empty list when `workspace_path` is `None`.
- [ ] Graph edge `retrieve_context → load_full_files → planner` is wired correctly.
- [ ] `DeveloperAgent.develop()` accepts `full_file_contexts` parameter.
- [ ] Developer prompt shows complete file content for each file in `plan.affected_files` when available.
- [ ] Developer prompt falls back to Qdrant chunks for files without full context.
- [ ] `PlannerAgent.plan()` accepts `full_file_contexts` parameter.
- [ ] Planner prompt includes full file content in the code context block.
- [ ] `graph.py` planner and developer node closures pass `state.full_file_contexts`.
- [ ] `mypy`/`pyright` type-checks cleanly — no untyped `list[FullFileContext]` usage.

---

## Architecture Impact

**Affected systems:**
- `forge_workflows` package: new state model, new node, updated edges.
- `forge_agents` package: new `FileLoader` utility, updated `DeveloperAgent` and `PlannerAgent` signatures.
- `BrainService`: no changes needed — it already sets `workspace_path` on state (Phase 2).

**Dependencies introduced:**
- `file_loader.py` imports `FullFileContext` from `forge_workflows.state`. This is a one-way dependency (agents → workflows state) that already exists for other models.

**Scalability concerns:**
- For the HTML MVP (2–3 files, 30–40 lines each) this is trivial. For large repos with many large files, passing entire file contents in LLM prompts will hit context limits. This is deferred: for the current phase, do not truncate.
- When large-repo support is needed, the mitigation is to limit `load_full_files` to files that appear in `plan.affected_files` (once the planner runs first), or truncate to the first N lines with a marker. Not needed now.

**Future extensions:**
- Phase 4 (PatchExecutor) reads from the same workspace files `FileLoader` already found. `FullFileContext.content` can be passed directly to `PatchExecutor` so Phase 4 does not need a second disk read.
- Phase 7 (Auto Repair Loop) can pass `FullFileContext` as the "original file" when asking the Developer to regenerate a failed patch.

---

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `workspace_path` is `None` when `load_full_files` runs | Low (Phase 2 sets it) | Node degrades gracefully to empty list; logs a warning |
| File exists in plan but not in workspace (e.g. new file to be created) | Medium | `FileLoader` skips missing files; Developer prompt notes the file is new |
| Full file content pushes LLM prompt past context window | Low for HTML MVP (30–40 lines) | Deferred; not a concern for the current target |
| Language detection produces wrong value for uncommon extensions | Low | Unknown extensions default to `None`; agents handle `None` gracefully |
| Phase 2 branch not yet merged when implementing Phase 3 | Certain (branches are separate) | Implement against Phase 2's interface as documented; merge Phase 2 first before running end-to-end |