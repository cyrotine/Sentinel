# Spec: Generate Skeleton

## Overview

This feature establishes the full monorepo directory structure, configuration files, and boilerplate required for Forge to exist as a buildable, runnable project. It creates every workspace (`apps/web`, `apps/api`, all `packages/*`) with minimal but real scaffolding — not mocks, not placeholders. Every package is importable, every app starts, every config is valid. Nothing is implemented beyond what is necessary to prove the structure works end-to-end.

Why it exists: no other feature can be built until the monorepo skeleton is in place. This is the root of the dependency tree.

How it contributes to autonomous software engineering: a clean, typed, layered skeleton enforces the architectural contracts that all six agents must honour from day one.

---

## Depends On

No dependencies.

---

## User Story

As a developer setting up Forge for the first time, I want to run a single bootstrap command and have a working monorepo with a running Next.js frontend, a running FastAPI backend, and all packages resolving their imports, so that I can immediately begin building agents without fighting tooling.

---

## Agent Changes

### Create

None — agents are implemented in later features.

### Modify

No agent changes.

---

## Workflow Changes

No workflow changes.

---

## Database Changes

### Create

No tables created in this feature. PostgreSQL connection config and Alembic migration scaffolding are wired up but no schema migrations are run.

---

## Retrieval Changes

No retrieval changes. Qdrant client config is wired up but no collections are created.

---

## API Changes

### Bootstrapped routes (health only)

**GET /api/health**

Response:
```json
{ "status": "ok", "version": "0.1.0" }
```

No request body.

---

## Frontend Changes

**Pages:**
- `/` — root page that renders a minimal `Dashboard` shell (empty state, no data)

**Components:**
- `AppShell` — sidebar + topbar layout wrapper
- `DashboardPage` — empty dashboard with placeholder cards

**State management:**
- No global state in this feature; server components only

---

## Files To Create

### Root

```
package.json              # Turborepo workspaces root
turbo.json                # Pipeline: build, dev, lint, test
tsconfig.base.json        # Shared TS config extended by all packages
.env.example              # All required env vars documented
docker-compose.yml        # PostgreSQL + Qdrant + api + web
.gitignore
```

### apps/web

```
apps/web/
  package.json
  tsconfig.json
  next.config.ts
  tailwind.config.ts
  postcss.config.mjs
  src/
    app/
      layout.tsx
      page.tsx
      globals.css
    components/
      app-shell.tsx
      dashboard-page.tsx
```

### apps/api

```
apps/api/
  pyproject.toml          # Python 3.12, FastAPI, Uvicorn, Pydantic v2, SQLAlchemy 2, Alembic, asyncpg, qdrant-client, langchain, langgraph
  Dockerfile
  alembic.ini
  alembic/
    env.py
    versions/             # empty, ready for first migration
  app/
    main.py               # FastAPI app factory
    config.py             # Settings via pydantic-settings
    api/
      __init__.py
      health.py           # GET /api/health
    services/
      __init__.py
    repositories/
      __init__.py
    models/
      __init__.py
    schemas/
      __init__.py
```

### packages/shared

```
packages/shared/
  package.json
  tsconfig.json
  src/
    index.ts              # re-exports
    types/
      index.ts            # shared TS types (WorkflowStatus, AgentRole, etc.)
```

### packages/agents

```
packages/agents/
  __init__.py
  base_agent.py           # Abstract BaseAgent with name, run() signature
```

### packages/workflows

```
packages/workflows/
  __init__.py
  state.py                # WorkflowState Pydantic model (stubs for all fields)
  graph.py                # Empty LangGraph StateGraph scaffold
```

### packages/github

```
packages/github/
  __init__.py
  client.py               # GitHubClient wrapping PyGithub / httpx
```

### packages/repository-analysis

```
packages/repository-analysis/
  __init__.py
  analyzer.py             # RepositoryAnalyzer stub (tree-sitter + GitPython)
```

### packages/vector-store

```
packages/vector-store/
  __init__.py
  store.py                # VectorStore wrapping qdrant-client
```

---

## Files To Modify

```
CLAUDE.md                 # Already exists — no changes needed in this feature
```

---

## New Packages

### JavaScript / Node

| Package | Purpose | Approval needed? |
|---|---|---|
| `turbo` | Monorepo task runner | No |
| `next` 15 | Frontend framework | No |
| `typescript` | Type checking | No |
| `tailwindcss` v4 | Styling | No |
| `shadcn/ui` | Component library | No |
| `react-flow` (xyflow) | Graph visualisation | No |
| `@types/node`, `@types/react` | Type stubs | No |

### Python

| Package | Purpose | Approval needed? |
|---|---|---|
| `fastapi[standard]` | API framework | No |
| `uvicorn[standard]` | ASGI server | No |
| `pydantic` v2 | Schema validation | No |
| `pydantic-settings` | Env config | No |
| `sqlalchemy[asyncio]` | ORM | No |
| `alembic` | Migrations | No |
| `asyncpg` | Async PostgreSQL driver | No |
| `qdrant-client` | Vector store | No |
| `langchain` | LLM tooling | No |
| `langgraph` | Agent workflow graph | No |
| `PyGithub` | GitHub API client | No |
| `gitpython` | Local git operations | No |
| `tree-sitter` | Code parsing | No |
| `httpx` | Async HTTP client | No |

---

## Implementation Rules

* TypeScript strict mode in all frontend and shared packages
* No `any` without explicit `// eslint-disable-next-line @typescript-eslint/no-explicit-any` and justification comment
* All Python schemas use Pydantic v2 `BaseModel`
* `WorkflowState` in `packages/workflows/state.py` is fully typed — no raw `dict` fields
* No business logic inside FastAPI route handlers — routes call services only
* Docker sandbox must be defined in `docker-compose.yml` before any code execution feature is built
* Vector store client must be initialised from env config, never hardcoded

---

## Definition Of Done

* [ ] `turbo dev` starts both `apps/web` (port 3000) and `apps/api` (port 8000) without errors
* [ ] `GET http://localhost:8000/api/health` returns `{"status": "ok", "version": "0.1.0"}`
* [ ] `http://localhost:3000` renders the dashboard shell without console errors
* [ ] `turbo build` completes successfully for all workspaces
* [ ] `turbo lint` passes with zero errors
* [ ] `docker-compose up` starts PostgreSQL and Qdrant without errors
* [ ] `apps/api` connects to PostgreSQL on startup (connection logged, no crash)
* [ ] `apps/api` connects to Qdrant on startup (connection logged, no crash)
* [ ] All Python packages import without errors (`python -c "from app.main import app"`)
* [ ] All TypeScript packages compile without errors (`tsc --noEmit`)
* [ ] `packages/workflows/state.py` exports a valid `WorkflowState` Pydantic model
* [ ] `packages/agents/base_agent.py` exports a valid abstract `BaseAgent`
* [ ] `.env.example` documents every required environment variable

---

## Architecture Impact

**Affected systems:** All — this is the root of the entire project.

**Dependencies introduced:**
- Turborepo ties all workspaces into a single build graph; all subsequent features must declare their workspace dependencies in `turbo.json`
- Pydantic v2 is the contract layer between workflow nodes; all agents must use it
- LangGraph `StateGraph` in `packages/workflows/graph.py` is the extension point for all agent features

**Scalability concerns:**
- Monorepo works well up to ~20 packages with Turborepo caching; beyond that, remote caching (Vercel Remote Cache) should be enabled
- `docker-compose.yml` is for local development only; production will need separate orchestration

**Future extensions:**
- `packages/execution-sandbox` (Docker-in-Docker or Dagger) will be added as a separate package in a later feature
- `packages/github` will be extended with webhook ingestion
- Additional LangGraph nodes slot into `graph.py` with no structural changes

---

## Risks

| Risk | Type | Mitigation |
|---|---|---|
| Next.js 15 + Tailwind v4 alpha API churn | Technical | Pin exact versions in `package.json`; upgrade deliberately |
| LangGraph API stability | Technical | Pin `langgraph==0.2.*`; isolate in `packages/workflows` |
| tree-sitter Python bindings installation on M-series Mac | Technical | Document `brew install tree-sitter` prerequisite in README |
| `asyncpg` cold-connect latency masking startup errors | Performance | Add explicit connection check with retry on startup |
| LLM not needed in this feature | LLM failure modes | N/A — no LLM calls in skeleton |
| Docker Desktop not running locally | Environment | `docker-compose up` guard in dev bootstrap script |
