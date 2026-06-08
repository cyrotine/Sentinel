# Forge

**An Autonomous Multi-Agent Open Source Engineer**

Forge understands a GitHub repository, analyzes issues, writes code, runs tests, reviews its own output, and opens pull requests — with minimal human intervention.

---

## What it does

1. Connect a GitHub repository
2. Forge clones it, parses every source file, and builds a vector knowledge base
3. Select an issue — Forge analyzes it, generates a plan, writes code, and runs tests
4. Receive a pull request draft

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15, TypeScript, Tailwind CSS |
| Backend | FastAPI, Python 3.12 |
| Database | PostgreSQL |
| Vector DB | Qdrant |
| AI Framework | LangGraph, LangChain |
| Embeddings | Google Gemini (`text-embedding-004`) |
| Code Analysis | tree-sitter, GitPython |
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
- A [GitHub Personal Access Token](https://github.com/settings/tokens) with `repo` scope
- A [Google AI API Key](https://aistudio.google.com/app/apikey) for Gemini embeddings

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/cyrotine/Sentinel.git
cd Sentinel
```

### 2. Install JavaScript dependencies

```bash
pnpm install
```

### 3. Install Python dependencies

```bash
uv sync
```

### 4. Start PostgreSQL and Qdrant with Docker

```bash
docker run -d \
  --name forge-postgres \
  -e POSTGRES_USER=forge \
  -e POSTGRES_PASSWORD=forge \
  -e POSTGRES_DB=forge \
  -p 5432:5432 \
  postgres:16

docker run -d \
  --name forge-qdrant \
  -p 6333:6333 \
  qdrant/qdrant
```

Verify both are running:

```bash
docker ps
```

### 5. Configure environment variables

```bash
cp .env.example apps/api/.env
```

Open `apps/api/.env` and fill in:

```env
GITHUB_TOKEN=ghp_your_token_here
GOOGLE_API_KEY=your_google_api_key_here
```

The rest of the defaults work as-is for local development.

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

1. Go to **Repositories** in the sidebar
2. Click **Connect Repository**
3. Paste any public GitHub URL, e.g. `https://github.com/octocat/Hello-World`
4. Watch Forge clone, analyze, and index the repository in real time
5. Once complete, explore the file tree, language breakdown, and open issues

---

## Project structure

```
Sentinel/
├── apps/
│   ├── api/                  # FastAPI backend
│   │   ├── app/
│   │   │   ├── api/          # Route handlers
│   │   │   ├── models/       # SQLAlchemy ORM models
│   │   │   ├── repositories/ # Database access layer
│   │   │   ├── schemas/      # Pydantic request/response schemas
│   │   │   └── services/     # Business logic
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
| `POST` | `/api/repositories` | Connect a repository and start ingestion |
| `GET` | `/api/repositories` | List all repositories |
| `GET` | `/api/repositories/{id}` | Get repository details and stats |
| `GET` | `/api/repositories/{id}/ingestion` | Get ingestion run status |
| `GET` | `/api/repositories/{id}/files` | List indexed files |
| `GET` | `/api/repositories/{id}/issues` | List issues |
| `POST` | `/api/repositories/{id}/ingest` | Re-trigger ingestion |
| `DELETE` | `/api/repositories/{id}` | Remove repository and its vectors |

Interactive docs available at [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Troubleshooting

**`GITHUB_TOKEN` not loaded / "Illegal header value"**
Make sure you copied `.env.example` to `apps/api/.env`, not just the repo root.

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
