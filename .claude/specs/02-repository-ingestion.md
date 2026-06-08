# Spec: Repository Ingestion

## Overview

Repository Ingestion is the process by which Forge transforms a raw GitHub repository into a structured, queryable knowledge base. It clones the repository, parses every source file with tree-sitter, splits content into semantic chunks, generates vector embeddings, and persists both structured metadata (PostgreSQL) and dense representations (Qdrant) for all downstream agents to consume.

Why it exists: every subsequent agent — Issue Analyzer, Planner, Developer, Reviewer — must understand the repository before it can reason about it. Ingestion is the one-time (and re-triggered) bootstrap that makes a repository "legible" to the rest of Forge.

How it contributes to autonomous software engineering: agents never read raw files at query time. They issue targeted vector searches against pre-indexed chunks. This keeps LLM context windows small and retrieval fast, which is the difference between a chatbot and an autonomous engineer.

---

## Depends On

- `01-generate-skeleton` — monorepo structure, `VectorStore` stub, `GitHubClient` stub, `RepositoryAnalyzer` stub, PostgreSQL + Qdrant connections, FastAPI app factory.

---

## User Story

As a developer, I want to paste a GitHub repository URL into Forge and watch it be analyzed automatically, so that I can immediately select issues and let Forge begin planning without any manual setup.

---

## Agent Changes

### Create

None. Repository ingestion runs as a background service job, not a LangGraph agent. It feeds the knowledge base that agents query later.

### Modify

**`RepositoryAnalyzer`** (`packages/repository-analysis/forge_repository_analysis/analyzer.py`)

Replace the stub with a real implementation:

- Clone repository via GitPython into a temp directory
- Walk the file tree; detect language per file via tree-sitter grammar lookup
- Parse each file with tree-sitter to extract top-level symbols (functions, classes, methods)
- Split file content into overlapping chunks (512 tokens, 64-token overlap)
- Return `RepositoryAnalysis` with full `FileNode` list and extracted `SymbolNode` list

**`GitHubClient`** (`packages/github/forge_github/client.py`)

Implement real API calls using `httpx`:

- `get_repository` — fetch metadata via `GET /repos/{owner}/{name}`
- `get_issues` — paginate `GET /repos/{owner}/{name}/issues?state=open`
- `create_pull_request` — `POST /repos/{owner}/{name}/pulls`
- Add: `get_file_tree(owner, name, sha)` — recursive tree fetch via `GET /repos/{owner}/{name}/git/trees/{sha}?recursive=1`

**`VectorStore`** (`packages/vector-store/forge_vector_store/store.py`)

Implement real Qdrant calls using `qdrant-client`:

- `create_collection` — create if not exists, configure cosine distance, vector size from settings
- `upsert` — batch upsert vectors with metadata payload
- `search` — semantic search with optional payload filters
- Add: `delete_collection(collection: str)` — used when a repository is removed

---

## Workflow Changes

Repository ingestion is **not** part of the primary LangGraph issue-resolution workflow. It is a separate background pipeline triggered by a user action (connecting a repository).

No changes to `packages/workflows/forge_workflows/graph.py` or `WorkflowState`.

The ingestion pipeline is implemented as an async background task in the FastAPI service layer.

**Ingestion pipeline order:**

```
Clone Repository
↓
Analyze Files (tree-sitter)
↓
Store Repository Metadata
↓
Fetch GitHub Issues
↓
Store Issues
↓
Generate Embeddings
↓
Mark ingestion_run completed
```

This makes ingestion a complete bootstrap: after it finishes, both the vector index and the issue list are ready for downstream agents.

---

## Database Changes

### Create

**`repositories`**

| Column | Type | Constraints |
|---|---|---|
| `id` | `UUID` | PK, default `gen_random_uuid()` |
| `github_id` | `BIGINT` | UNIQUE NOT NULL |
| `owner` | `VARCHAR(255)` | NOT NULL |
| `name` | `VARCHAR(255)` | NOT NULL |
| `full_name` | `VARCHAR(511)` | NOT NULL |
| `description` | `TEXT` | NULLABLE |
| `default_branch` | `VARCHAR(255)` | NOT NULL, default `'main'` |
| `github_url` | `TEXT` | NOT NULL |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` |

---

**`ingestion_runs`**

| Column | Type | Constraints |
|---|---|---|
| `id` | `UUID` | PK, default `gen_random_uuid()` |
| `repository_id` | `UUID` | FK → `repositories.id` ON DELETE CASCADE |
| `status` | `VARCHAR(50)` | NOT NULL — `pending`, `cloning`, `analyzing`, `embedding`, `completed`, `failed` |
| `total_files` | `INT` | NULLABLE |
| `processed_files` | `INT` | NOT NULL, default `0` |
| `error` | `TEXT` | NULLABLE |
| `started_at` | `TIMESTAMPTZ` | NULLABLE |
| `completed_at` | `TIMESTAMPTZ` | NULLABLE |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` |

---

**`repository_files`**

| Column | Type | Constraints |
|---|---|---|
| `id` | `UUID` | PK, default `gen_random_uuid()` |
| `repository_id` | `UUID` | FK → `repositories.id` ON DELETE CASCADE |
| `path` | `TEXT` | NOT NULL |
| `language` | `VARCHAR(100)` | NULLABLE |
| `size_bytes` | `INT` | NOT NULL, default `0` |
| `chunk_count` | `INT` | NOT NULL, default `0` |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` |
| UNIQUE | | `(repository_id, path)` |

---

**`issues`**

| Column | Type | Constraints |
|---|---|---|
| `id` | `UUID` | PK, default `gen_random_uuid()` |
| `repository_id` | `UUID` | FK → `repositories.id` ON DELETE CASCADE |
| `github_issue_id` | `BIGINT` | UNIQUE NOT NULL |
| `number` | `INT` | NOT NULL |
| `title` | `TEXT` | NOT NULL |
| `body` | `TEXT` | NULLABLE |
| `state` | `VARCHAR(20)` | NOT NULL — `open`, `closed` |
| `labels` | `JSONB` | NOT NULL, default `'[]'` |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, default `now()` |

---

### Modify

No existing tables modified.

---

## Retrieval Changes

### New Collection

**`repo_{repository_id}`** (one Qdrant collection per repository)

- Vector size: `1536` (OpenAI `text-embedding-3-small`)
- Distance: Cosine

Payload schema per point:

```json
{
  "repository_id": "uuid",
  "file_path": "src/utils/parser.py",
  "language": "python",
  "chunk_index": 0,
  "start_line": 1,
  "end_line": 64,
  "symbol": "parse_expression",
  "content": "raw chunk text"
}
```

Points are keyed by deterministic UUID derived from `sha256(repository_id + file_path + chunk_index)` so re-ingestion is idempotent via upsert.

### Embedding Provider

`langchain_openai.OpenAIEmbeddings` with model `text-embedding-3-small`.

Provider and model are configurable via `Settings.embedding_model` and `Settings.openai_api_key`.

---

## API Changes

All routes under prefix `/api/repositories`.

---

### `POST /api/repositories`

Register a repository and trigger ingestion.

**Request:**
```json
{
  "github_url": "https://github.com/vercel/next.js"
}
```

Backend extracts `owner` and `name` from the URL. Supports both `https://github.com/{owner}/{name}` and `https://github.com/{owner}/{name}.git`.

**Response `202 Accepted`:**
```json
{
  "repository_id": "uuid",
  "ingestion_run_id": "uuid",
  "status": "pending"
}
```

Ingestion runs in the background via `asyncio.create_task`. Returns immediately.

---

### `GET /api/repositories`

List all registered repositories.

**Response `200`:**
```json
[
  {
    "id": "uuid",
    "owner": "octocat",
    "name": "Hello-World",
    "full_name": "octocat/Hello-World",
    "description": "...",
    "github_url": "https://github.com/octocat/Hello-World",
    "latest_ingestion": {
      "id": "uuid",
      "status": "completed",
      "total_files": 42,
      "processed_files": 42,
      "completed_at": "2026-06-08T10:00:00Z"
    }
  }
]
```

---

### `GET /api/repositories/{repository_id}`

Get a single repository with its latest ingestion run.

**Response `200`:**
```json
{
  "id": "uuid",
  "owner": "octocat",
  "name": "Hello-World",
  "full_name": "octocat/Hello-World",
  "description": "...",
  "github_url": "https://github.com/octocat/Hello-World",
  "default_branch": "main",
  "created_at": "2026-06-08T10:00:00Z",
  "stats": {
    "total_files": 432,
    "total_chunks": 8123,
    "open_issues": 67
  },
  "latest_ingestion": { ... }
}
```

**Response `404`** if not found.

---

### `GET /api/repositories/{repository_id}/files`

List analyzed files for a repository.

**Query params:** `language` (optional filter), `limit` (default 100), `offset` (default 0)

**Response `200`:**
```json
{
  "total": 42,
  "files": [
    {
      "id": "uuid",
      "path": "src/utils/parser.py",
      "language": "python",
      "size_bytes": 1024,
      "chunk_count": 4
    }
  ]
}
```

---

### `GET /api/repositories/{repository_id}/ingestion`

Get the latest ingestion run status for a repository. Used for polling from the frontend.

**Response `200`:**
```json
{
  "id": "uuid",
  "status": "analyzing",
  "total_files": 200,
  "processed_files": 87,
  "error": null,
  "started_at": "2026-06-08T10:00:00Z",
  "completed_at": null
}
```

---

### `GET /api/repositories/{repository_id}/issues`

List stored issues for a repository. No analysis, no ranking — pure retrieval.

**Query params:** `state` (default `open`), `limit` (default 50), `offset` (default 0)

**Response `200`:**
```json
{
  "total": 42,
  "issues": [
    {
      "id": "uuid",
      "number": 103,
      "title": "Fix cart persistence",
      "state": "open",
      "labels": ["bug"]
    }
  ]
}
```

---

### `POST /api/repositories/{repository_id}/ingest`

Re-trigger ingestion for an existing repository (force re-index).

**Response `202`:**
```json
{
  "ingestion_run_id": "uuid",
  "status": "pending"
}
```

---

## Frontend Changes

### Pages

**`/repositories`** (`apps/web/src/app/repositories/page.tsx`)

- List of connected repositories as cards
- Each card shows: `owner/name`, description, language breakdown bar, ingestion status badge, file count
- "Connect Repository" button opens a modal with a single GitHub URL input
- On submit, calls `POST /api/repositories` with `{"github_url": "..."}` and shows a toast notification

**`/repositories/[id]`** (`apps/web/src/app/repositories/[id]/page.tsx`)

- Repository header: name, description, GitHub link
- Stats bar: total files, total chunks, open issue count
- Ingestion progress bar (polls `GET /api/repositories/{id}/ingestion` every 2 seconds while status is not `completed` or `failed`)
- File tree panel: searchable list of files grouped by language
- Language distribution chart (horizontal bar)
- Open issues list (read-only) — number, title, labels; issue selection belongs in a later feature

### Components

| Component | Path | Purpose |
|---|---|---|
| `RepositoryCard` | `src/components/repositories/repository-card.tsx` | Card for repository list |
| `ConnectRepositoryModal` | `src/components/repositories/connect-repository-modal.tsx` | Form modal to register a repo |
| `IngestionProgress` | `src/components/repositories/ingestion-progress.tsx` | Polling progress indicator |
| `FileTree` | `src/components/repositories/file-tree.tsx` | Grouped, searchable file list |
| `LanguageBreakdown` | `src/components/repositories/language-breakdown.tsx` | Horizontal bar chart of language distribution |
| `IssuesList` | `src/components/repositories/issues-list.tsx` | Read-only list of repository issues |
| `StatusBadge` | `src/components/ui/status-badge.tsx` | Reusable pill for ingestion/workflow status |

### State management

- Repository list: server component fetches on page load
- Ingestion status: client component polls with `setInterval` (clears when `completed` or `failed`)
- No global state store — data is co-located with components

### Dashboard update

Add a "Repositories" summary card to `dashboard-page.tsx` showing count of connected repositories and count with completed ingestion.

---

## Files To Modify

```
packages/repository-analysis/forge_repository_analysis/analyzer.py   # Full implementation
packages/github/forge_github/client.py                                # Full implementation
packages/vector-store/forge_vector_store/store.py                     # Full implementation
apps/api/app/config.py                                                # Add openai_api_key, embedding_model, clone_base_dir
apps/api/app/main.py                                                  # Include repositories router
apps/web/src/components/dashboard-page.tsx                            # Add repositories summary card
```

---

## Files To Create

### Backend

```
apps/api/app/api/repositories.py              # FastAPI router — all /api/repositories routes
apps/api/app/services/ingestion_service.py    # IngestionService — orchestrates the full pipeline
apps/api/app/services/repository_service.py  # RepositoryService — CRUD for repositories + files + issues
apps/api/app/repositories/repository_repo.py  # SQLAlchemy async queries for repositories table
apps/api/app/repositories/ingestion_repo.py   # SQLAlchemy async queries for ingestion_runs table
apps/api/app/repositories/file_repo.py        # SQLAlchemy async queries for repository_files table
apps/api/app/repositories/issue_repo.py       # SQLAlchemy async queries for issues table
apps/api/app/models/repository.py             # SQLAlchemy ORM model for repositories
apps/api/app/models/ingestion_run.py          # SQLAlchemy ORM model for ingestion_runs
apps/api/app/models/repository_file.py        # SQLAlchemy ORM model for repository_files
apps/api/app/models/issue.py                  # SQLAlchemy ORM model for issues
apps/api/app/schemas/repository.py            # Pydantic schemas: RepositoryCreate (github_url), RepositoryOut, IngestionRunOut, FileOut, IssueOut, RepositoryStats
apps/api/alembic/versions/001_create_repositories_tables.py  # Alembic migration (repositories, ingestion_runs, repository_files, issues)
```

### Packages

```
packages/repository-analysis/forge_repository_analysis/chunker.py    # CodeChunker: splits file content into overlapping token windows
packages/repository-analysis/forge_repository_analysis/embedder.py   # CodeEmbedder: wraps LangChain OpenAIEmbeddings
packages/repository-analysis/forge_repository_analysis/languages.py  # LANGUAGE_MAP: extension → tree-sitter grammar name
```

### Frontend

```
apps/web/src/app/repositories/page.tsx
apps/web/src/app/repositories/[id]/page.tsx
apps/web/src/components/repositories/repository-card.tsx
apps/web/src/components/repositories/connect-repository-modal.tsx
apps/web/src/components/repositories/ingestion-progress.tsx
apps/web/src/components/repositories/file-tree.tsx
apps/web/src/components/repositories/language-breakdown.tsx
apps/web/src/components/repositories/issues-list.tsx
apps/web/src/components/ui/status-badge.tsx
apps/web/src/lib/api.ts                       # Typed fetch wrapper for all API calls
```

---

## New Packages

### Python

| Package | Purpose | Approval needed? |
|---|---|---|
| `gitpython` | Clone and inspect git repositories | Already in pyproject.toml |
| `tree-sitter` | Parse source files to ASTs | Already in pyproject.toml |
| `tree-sitter-languages` | Pre-built grammars for 40+ languages | **Flag: new dependency** — bundles many language parsers, ~50 MB wheel |
| `langchain-openai` | OpenAI embeddings via LangChain | **Flag: requires `OPENAI_API_KEY`** |
| `tiktoken` | Token counting for chunk splitting | No — installs with langchain-openai |

### JavaScript

No new JS packages. All UI components use shadcn/ui (already installed) and native `fetch`.

---

## Implementation Rules

- TypeScript strict mode; no `any`
- All Pydantic models use `model_config = ConfigDict(from_attributes=True)` for ORM mapping
- `IngestionService` must not be called from inside a route handler body — routes call service, service spawns background task
- SQLAlchemy sessions must be scoped to request via `AsyncSession` dependency injection
- Cloned repositories must be written to a temp directory (`settings.clone_base_dir`) and cleaned up after embedding — never leave raw clones on disk permanently
- Qdrant upsert must be batched (max 100 vectors per call) to avoid timeout on large repositories
- All embeddings must be deterministically keyed so re-ingestion is safe (upsert, not insert)
- Never pass raw dict between repository layer and service layer — use Pydantic schemas at the boundary
- Polling interval on the frontend must clear its interval handle on component unmount to avoid memory leaks
- No business logic inside FastAPI route handlers

---

## Definition Of Done

- [ ] `POST /api/repositories` with `{"owner": "octocat", "name": "Hello-World"}` returns `202` with `ingestion_run_id`
- [ ] Ingestion pipeline clones the repository to temp dir, deletes it after embedding
- [ ] `GET /api/repositories/{id}/ingestion` returns `status: "completed"` after a small public repo finishes
- [ ] `GET /api/repositories/{id}/files` lists parsed files with `language` populated
- [ ] Qdrant collection `repo_{repository_id}` contains embeddings after ingestion completes
- [ ] Vector search on the collection returns semantically relevant chunks for a query string
- [ ] Alembic migration `001_create_repositories_tables` runs without error on a clean database
- [ ] `GET /api/repositories` lists all connected repositories
- [ ] `/repositories` page renders the repository list without errors
- [ ] "Connect Repository" modal submits and triggers ingestion; toast appears
- [ ] `/repositories/{id}` page shows ingestion progress bar that updates until completion
- [ ] Progress bar disappears and file list appears when ingestion reaches `completed`
- [ ] `StatusBadge` renders correct color for each ingestion status (`pending`, `analyzing`, `completed`, `failed`)
- [ ] Re-triggering ingestion via `POST /api/repositories/{id}/ingest` creates a new `ingestion_run` row and re-indexes
- [ ] Repository with 0 supported-language files completes ingestion gracefully with `total_files: 0`
- [ ] Issues are fetched from GitHub and persisted to the `issues` table during ingestion
- [ ] `GET /api/repositories/{id}/issues` returns stored issues with correct `number`, `title`, `state`, `labels`
- [ ] Repository detail page displays open issue count in the stats bar
- [ ] Repository detail page renders the issues list below the file tree
- [ ] `turbo lint` passes with zero errors after all new files are added

---

## Architecture Impact

**Affected systems:**

- `apps/api` — gains three new routers, three service classes, three repository classes, three ORM models, one Alembic migration
- `packages/repository-analysis` — stubs replaced with production implementations
- `packages/github` — stub replaced with real `httpx`-backed client
- `packages/vector-store` — stub replaced with real `qdrant-client` implementation
- `apps/web` — two new pages, seven new components

**Dependencies introduced:**

- `tree-sitter-languages` adds a large (~50 MB) compiled wheel; CI must cache pip properly
- `langchain-openai` introduces a runtime dependency on `OPENAI_API_KEY`; the app will raise a startup error if the key is missing and embedding is attempted
- Qdrant becomes a write dependency, not just a health-check target; the Qdrant service in `docker-compose.yml` must be healthy before ingestion can complete

**Scalability concerns:**

- Large monorepos (>10,000 files) will hit Qdrant upsert time limits without batching — the 100-vector batch cap must be enforced
- Embedding 10,000 chunks against OpenAI API at ~$0.00002/1K tokens is negligible for MVP but should be tracked
- Background tasks with `asyncio.create_task` are fire-and-forget; if the API process restarts mid-ingestion, the run will be stuck in `analyzing` — add a startup check that resets `running` ingestions to `failed`

**Future extensions:**

- Webhook-triggered re-ingestion on push events (adds to `packages/github`)
- Differential re-ingestion (only re-embed changed files based on git diff)
- Support for local (non-GitHub) repositories via direct path input
- `packages/execution-sandbox` will mount the cloned repo for code execution — the clone path strategy used here must be compatible

---

## Risks

| Risk | Type | Mitigation |
|---|---|---|
| `tree-sitter-languages` grammar missing for a language | Technical | Fall back to plain-text chunking when grammar not found; log a warning |
| GitHub API rate limit (60 req/hr unauthenticated, 5000/hr authenticated) | Technical | Always use `GITHUB_TOKEN`; add `Retry-After` header handling in `GitHubClient` |
| OpenAI embedding API timeout on large batches | Technical | Batch at 100 chunks max; add retry with exponential backoff via `tenacity` |
| Repository clone fails (private repo, bad credentials) | Technical | Surface error in `ingestion_run.error` column; return clear message via API |
| Qdrant collection name collision if repository is deleted and re-added | Technical | Use stable `repo_{repository_id}` naming; UUID ensures no collision |
| Frontend polling loop not cleaned up on navigation | Performance | `useEffect` cleanup returns `clearInterval`; enforce with ESLint `react-hooks/exhaustive-deps` |
| LLM embedding produces null vector for empty file | LLM failure mode | Skip files with 0 tokens; record `chunk_count: 0` in `repository_files` |
| Disk exhaustion from uncleaned clones on crash | Infrastructure | Startup task scans `clone_base_dir` for stale directories older than 1 hour and removes them |
