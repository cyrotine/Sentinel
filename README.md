# Forge

**An Autonomous Multi-Agent Open Source Engineer**

Forge understands a GitHub repository, analyzes issues, plans an implementation, writes code, runs tests, reviews its own output, pushes a branch, and opens a real pull request — with minimal human intervention.

---

## What it does

1. **Connect** a GitHub repository (with a Personal Access Token)
2. Forge **ingests** it — clones the repo, parses every source file with tree-sitter, and builds a Qdrant vector knowledge base
3. **Select an issue** and start an agent run
4. A LangGraph pipeline takes over: **Issue Analyzer → Planner → Developer → QA → Reviewer → PR Generator**
5. Forge applies its patches in an isolated workspace, **commits and pushes a branch**, and **opens a real pull request**

```mermaid
flowchart LR
  Connect[Connect repo + PAT] --> Ingest[Ingest: clone, tree-sitter,<br/>embed to Qdrant]
  Ingest --> Pick[Select an issue]
  Pick --> Run
  subgraph Run[Agent Run · LangGraph]
    A[Issue Analyzer] --> P[Planner] --> D[Developer] --> Q[QA / Test] --> R[Reviewer] --> G[PR Generator]
  end
  Run --> Patch[Apply patches in workspace]
  Patch --> Git[Branch · commit · push]
  Git --> PR[Open real GitHub PR]
```

> Test execution is currently simulated by the QA agent (LLM reasoning) for the static-file target profile. Real sandboxed test execution is a future phase.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15, TypeScript, Tailwind CSS |
| Backend | FastAPI, Python 3.12 |
| Database | PostgreSQL |
| Vector DB | Qdrant |
| AI Framework | LangGraph, LangChain |
| Embeddings | Google Gemini (`models/gemini-embedding-001`) |
| Agent LLM | Google Gemini (`gemini-2.5-flash`) |
| Code Analysis | tree-sitter, GitPython |
| Git & PR Automation | GitPython + GitHub REST API |
| Monorepo | Turborepo, pnpm, uv |

---

## Prerequisites

Install these before cloning:

- [Node.js 20+](https://nodejs.org) and [pnpm](https://pnpm.io/installation)
  ```bash
  npm install -g pnpm
  ```
- [Python 3.12+](https://www.python.org/downloads/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- [Docker](https://www.docker.com/products/docker-desktop) (for PostgreSQL and Qdrant)
- A [GitHub Personal Access Token](https://github.com/settings/tokens) with `repo` scope (required for pushing branches and opening pull requests)
- A [Google AI API Key](https://aistudio.google.com/app/apikey) for Gemini embeddings and the agent LLM

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/cyrotine/Sentinel.git
cd Forge
```

### 2. Install JavaScript dependencies

```bash
pnpm install
```

### 3. Install Python dependencies

```bash
uv sync
```

### 4. Start PostgreSQL and Qdrant

The repo ships a `docker-compose.yml` with both services preconfigured:

```bash
docker compose up -d
```

Verify both are running:

```bash
docker compose ps
```

### 5. Configure environment variables

The backend loads `.env` from the repo root (it also reads `apps/api/.env`, with the repo-root file taking precedence). Copy the example to the repo root:

```bash
cp .env.example .env
```

`.env.example` contains:

```env
# PostgreSQL
DATABASE_URL=postgresql+asyncpg://forge:forge@localhost:5432/forge

# Qdrant
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=

# GitHub
GITHUB_TOKEN=

# Google (embeddings + agent LLM)
GOOGLE_API_KEY=
EMBEDDING_MODEL=models/gemini-embedding-001

# Ingestion
CLONE_BASE_DIR=/tmp/forge_clones

# API
API_PORT=8000
DEBUG=true

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000/api
```

You only need to fill in two values:

- `GITHUB_TOKEN` — a PAT with `repo` scope
- `GOOGLE_API_KEY` — your Google AI key

The rest of the defaults work as-is for local development. `NEXT_PUBLIC_API_URL` is optional locally — the frontend falls back to `http://127.0.0.1:8000/api`.

### 6. Run database migrations

```bash
cd apps/api
uv run alembic upgrade head
cd ../..
```

---

## Running the app

Open two terminals.

**Terminal 1 — Backend**

```bash
cd apps/api
uv run uvicorn app.main:app --reload --port 8000
```

You should see:

```
INFO:     PostgreSQL connected
INFO:     Qdrant connected
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Terminal 2 — Frontend**

```bash
cd apps/web
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000)

---

## First use

### Connect and ingest a repository

1. Go to **Repositories** in the sidebar
2. Click **Connect Repository**
3. Paste a public GitHub URL (e.g. `https://github.com/octocat/Hello-World`) and, if you want Forge to push branches and open PRs, provide a PAT with `repo` scope
4. Watch Forge clone, analyze, and index the repository in real time
5. Once complete, explore the file tree, language breakdown, and open issues

### Run the autonomous pipeline

6. Open an indexed repository and pick an **issue**
7. Start an **agent run**
8. On the run detail page (`/agents/{runId}`), watch the live pipeline advance through Issue Analyzer → Planner → Developer → QA → Reviewer → PR Generator
9. Inspect the syntax-highlighted diffs for each changed file
10. When the run completes, Forge has pushed a branch and **opened a real pull request** on the target repository

> Pushing branches and creating PRs requires the repository's PAT (`repo` scope). Without it, Forge still analyzes, plans, and generates patches, but cannot complete the push/PR step.

---

## Project structure

```
Forge/
├── apps/
│   ├── api/                  # FastAPI backend
│   │   ├── app/
│   │   │   ├── api/          # Route handlers
│   │   │   ├── models/       # SQLAlchemy ORM models
│   │   │   ├── repositories/ # Database access layer
│   │   │   ├── schemas/      # Pydantic request/response schemas
│   │   │   └── services/     # Business logic
│   │   │       ├── ingestion_service.py    # Clone → analyze → embed
│   │   │       ├── workspace_manager.py    # Per-run isolated clones
│   │   │       ├── brain_service.py        # Drives the LangGraph pipeline
│   │   │       ├── git_service.py          # Branch, commit, push
│   │   │       └── github_pr_service.py    # Real PR creation via REST API
│   │   └── alembic/          # Database migrations
│   └── web/                  # Next.js 15 frontend
│       └── src/
│           ├── app/          # Pages (App Router)
│           ├── components/   # UI components
│           └── lib/          # API client
├── packages/
│   ├── agents/               # LangGraph agent definitions
│   ├── github/               # GitHub API client
│   ├── repository-analysis/  # Tree-sitter + chunker + embedder
│   ├── vector-store/         # Qdrant client wrapper
│   ├── workflows/            # LangGraph workflow graph
│   └── shared/               # Shared types
└── turbo.json
```

---

## API reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/repositories` | Connect a repository (optional `github_pat`) and start ingestion |
| `GET` | `/api/repositories` | List all repositories |
| `GET` | `/api/repositories/{id}` | Get repository details and stats |
| `GET` | `/api/repositories/{id}/ingestion` | Get ingestion run status |
| `POST` | `/api/repositories/{id}/ingest` | Re-trigger ingestion |
| `GET` | `/api/repositories/{id}/files` | List indexed files |
| `GET` | `/api/repositories/{id}/issues` | List issues |
| `DELETE` | `/api/repositories/{id}` | Remove repository and its vectors |
| `POST` | `/api/agent-runs` | Start an agent run on a target issue |
| `GET` | `/api/agent-runs` | List agent runs (filter by `repository_id`) |
| `GET` | `/api/agent-runs/{run_id}` | Get run details and the live result snapshot |

Interactive docs available at [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Troubleshooting

**`GITHUB_TOKEN` not loaded / "Illegal header value"**
The backend loads both the repo-root `.env` and `apps/api/.env`, with the repo-root file taking precedence. Make sure at least one of them exists and contains your token.

**`the number of query arguments cannot exceed 32767`**
This was a known issue with large repositories. It is fixed — file and issue inserts are batched at 500 rows per statement.

**`Vector dimension error: expected dim X, got Y`**
The Qdrant collection from a previous ingestion has a stale dimension. Delete and re-add the repository — each ingestion now detects the actual embedding dimension dynamically and recreates the collection fresh.

**Alembic `No script_location key found`**
Run alembic from inside `apps/api/`, not the repo root:
```bash
cd apps/api && uv run alembic upgrade head
```

**Port already in use**
```bash
# Kill whatever is on port 8000 or 3000
lsof -ti :8000 | xargs kill
lsof -ti :3000 | xargs kill
```
