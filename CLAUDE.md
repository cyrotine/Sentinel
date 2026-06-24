# CLAUDE.md

# Forge

### An Autonomous Multi-Agent Open Source Engineer

---

## Project Vision

Forge is an autonomous software engineering platform capable of understanding software repositories, analyzing issues, planning implementations, generating code, validating changes, reviewing solutions, and preparing pull requests with minimal human intervention.

The goal is not to build another coding chatbot.

The goal is to build a system that can:

1. Understand a repository
2. Understand an issue
3. Decide what should be done
4. Generate implementation plans
5. Write code
6. Run tests
7. Review itself
8. Generate pull requests

Forge should behave like a small autonomous engineering team.

---

# Core Principle

Every feature should contribute to one of these capabilities:

* Think
* Decide
* Act

Avoid features that only generate text.

Prioritize execution over conversation.

---

# Tech Stack

Frontend:

* Next.js 15
* TypeScript
* Tailwind CSS
* shadcn/ui
* React Flow

Backend:

* FastAPI
* Python 3.12

Database:

* PostgreSQL

Vector Database:

* Qdrant

AI Framework:

* LangGraph
* LangChain

Repository Analysis:

* Tree-sitter
* GitPython
* GitHub API

Execution Sandbox:

* Docker

---

# Project Structure

apps/
├── web/
├── api/

packages/
├── agents/
├── workflows/
├── github/
├── repository-analysis/
├── vector-store/
├── shared/

---

# Development Philosophy

Follow these rules strictly:

1. Keep modules small and focused.
2. Prefer composition over inheritance.
3. Avoid unnecessary abstractions.
4. Every service should have a single responsibility.
5. Every feature must be production-ready.
6. Never introduce mock implementations unless explicitly requested.
7. Prefer type safety everywhere.
8. Avoid code duplication.

---

# Agent Architecture

Forge contains six primary agents.

## Issue Analyzer Agent

Responsibilities:

* Read GitHub issues
* Classify issue type
* Estimate difficulty
* Estimate impact
* Produce structured issue metadata

Output:

{
issueType: string,
severity: string,
confidence: number,
impact: number
}

---

## Planner Agent

Responsibilities:

* Analyze issue
* Identify affected files
* Generate implementation strategy
* Create execution graph

Output:

{
tasks: [],
affectedFiles: [],
dependencies: []
}

---

## Developer Agent

Responsibilities:

* Generate code changes
* Modify files
* Create patches
* Implement solutions

Never directly commit code.

---

## QA Agent

Responsibilities:

* Generate tests
* Run tests
* Evaluate coverage
* Report failures

---

## Reviewer Agent

Responsibilities:

* Review generated code
* Identify bugs
* Detect security risks
* Suggest improvements

---

## PR Agent

Responsibilities:

* Generate pull request title
* Generate pull request description
* Summarize modifications
* Generate release notes

---

# LangGraph Workflow

Issue Analyzer
↓
Planner
↓
Developer
↓
QA
↓
Reviewer
↓
PR Agent

Agents communicate only through structured state.

No free-form communication.

---

# State Management

Every workflow state must be represented by typed schemas.

Use Pydantic models.

Never pass raw dictionaries between workflow nodes.

Example:

class WorkflowState(BaseModel):
repository_id: str
issue_id: str
plan: Plan
code_changes: list
test_results: list

---

# Backend Standards

Use:

* FastAPI routers
* Service layer
* Repository layer

Structure:

api/
services/
repositories/
models/
schemas/

Avoid business logic inside route handlers.

---

# Frontend Standards

Pages:

* Dashboard
* Repository Overview
* Agent Center
* Issue Explorer
* Planning Board
* Execution Timeline
* Pull Request Center

Use:

* Server Components where possible
* Client Components only when necessary

Avoid excessive state management libraries.

---

# UI Principles

Dashboard should feel like:

GitHub × Linear × Cursor × Datadog

Requirements:

* Clean
* Fast
* Technical
* Real-time

Avoid flashy animations.

Prioritize clarity.

---

# Visualizations

Required:

1. Repository Knowledge Graph
2. Agent Workflow Graph
3. Execution Timeline
4. Issue Priority Matrix
5. Test Coverage Dashboard

Use React Flow whenever graph relationships exist.

---

# GitHub Integration

Capabilities:

* Fetch repositories
* Fetch issues
* Fetch pull requests
* Read commit history
* Create pull requests

Never perform destructive actions.

No force pushes.
No branch deletion.

---

# Security Rules

Never execute generated code directly on host machine.

Always use Docker sandbox execution.

Validate all user inputs.

Never expose API keys to frontend.

---

# AI Guidelines

When generating code:

1. Prefer minimal changes.
2. Preserve existing architecture.
3. Preserve coding style.
4. Avoid unnecessary refactors.
5. Generate tests whenever possible.
6. Explain reasoning through structured metadata.

---

# MVP Scope

Round 1 must include:

* Repository ingestion
* Repository understanding
* Issue analysis
* Planning agent
* Developer agent
* Test execution
* Reviewer agent
* PR generation
* Interactive dashboard

Everything else is secondary.

---

# Success Metric

A user should be able to:

1. Connect a repository
2. Select an issue
3. Watch Forge analyze the issue
4. Watch Forge create a plan
5. Watch Forge generate code
6. Watch Forge run tests
7. Watch Forge review itself
8. Receive a pull request draft

If this workflow works end-to-end, the MVP is successful.

---

# Roadmap: PR Draft Generator → Autonomous GitHub Engineer

## Current Implementation Status

```
Repository Ingestion      ✅ done
Repository Analysis       ✅ done
Issue Retrieval           ✅ done
Issue Selection           ✅ done
Context Retrieval         ✅ done
Implementation Planning   ✅ done
Patch Generation          ✅ done (LLM-generated unified diffs)
Code Review               ✅ done (LLM-based reviewer)
PR Draft Generation       ✅ done (title + body, no real PR created)

WorkspaceManager          ❌ not started
Full File Retrieval        ❌ not started
Patch Executor            ❌ not started
Git Operations            ❌ not started
GitHub PR Creation        ❌ not started
Real Test Execution       ✅ done (local: html-validate + DOM/content assertions)
Docker Sandbox            ❌ deferred (see below)
```

Test execution is now **real and local**: the `TestDesignerAgent` authors executable
`TestSpec`s after the planner (before the developer), and the `test_agent` node runs them
for real via the `SandboxRunner` (`html-validate` CLI + in-process BeautifulSoup/regex
assertions). The LLM-simulated `TestAgent` is no longer wired into the graph. The
`ValidatorAgent` still reasons about code using the LLM. Real execution currently runs as a
**local subprocess** (no Docker); the Docker/managed sandbox remains deferred and is the
prerequisite before exposing execution to deployed/untrusted traffic.

---

## Architectural Decisions (locked)

### GitHub Authentication (write operations)

Forge uses the user's **Personal Access Token (PAT)** for all write operations.

Rules:
- The PAT is collected during repository connection.
- Store it encrypted in the database. Never log it. Never send it to the frontend.
- Use it for: pushing branches, creating pull requests.
- Scope required from the user: `repo` (full control of private repositories).

Never implement GitHub App or OAuth flow unless explicitly requested.

### Repository Workspace

Each agent run clones the target repository to a **temporary directory on the API host**.

Rules:
- Clone path: `/tmp/forge-workspaces/{agent_run_id}/`
- Clone once per agent run at the start of the pipeline.
- The `WorkspaceManager` is responsible for clone, cleanup, and path resolution.
- Cleanup always runs on run completion (success or failure).
- Never reuse a workspace across runs.

### Full File Retrieval

Agents receive **complete file contents** read directly from the cloned workspace on disk.

Rules:
- Do NOT fetch file contents via the GitHub API (rate limits, latency).
- Do NOT rely solely on Qdrant chunks — chunks are for search, not for editing.
- The `FileLoader` reads full files from the workspace path.
- Files are passed to the DeveloperAgent alongside Qdrant chunks.

### Patch Application

The `PatchExecutor` applies unified diffs generated by the `DeveloperAgent` to the workspace.

Failure strategy: if a patch does not apply cleanly, send the **full file content + failed patch** back to the DeveloperAgent and ask it to regenerate. This counts against `max_iterations`.

Never silently swallow patch failures. Surface them in the agent run status.

### Docker Sandbox

**Deferred.** Do not implement Docker execution until the core pipeline (workspace → patch → git → PR) works end-to-end on real repositories.

The immediate target is **static HTML/CSS repositories** (2–3 files, 30–40 lines each). No build tooling, no test runner, no execution risk for this phase.

Remove the rule "Always use Docker sandbox execution" from Security Rules for this phase — it does not apply to static file patching.

### Test Execution

**Real and local (test-first) for HTML/static repos.** The pipeline now writes tests
*before* code and runs them for real:

- `TestDesignerAgent` runs after the planner and before the developer, deriving executable
  `TestSpec`s from the issue's acceptance criteria (true TDD).
- The `test_agent` node executes those specs via the `SandboxRunner`
  (`packages/agents/forge_agents/sandbox_runner.py`): the real `html-validate` CLI for HTML
  validity, plus in-process BeautifulSoup/regex evaluation for DOM/content assertions.
- Failing tests feed the auto-repair loop (`tests_failed` trigger) so the developer
  regenerates code to make them pass, bounded by `max_iterations`.

Execution runs as a **local subprocess** behind a swappable `SandboxRunner` interface.
Generated test artifacts are never written into the workspace (html-validate config is a
temp file; assertions read files in-memory), so the git tree stays clean.

Broader real test runners (`pytest`, `npm test`, etc.) and untrusted/deployed execution
remain a future phase, implemented only after Docker isolation is in place (Phase 10).

---

## Implementation Phases

### Phase 1 — Surface Real Diffs in UI
**Priority: HIGH | Effort: 1–2 days**

Render `CodeChange.patch` as a real diff in `agent-run-detail.tsx`.

- Add a diff viewer component (syntax-highlighted, unified format).
- Add copy-to-clipboard on each diff block.
- This is a frontend-only change. No backend work needed.

### Phase 2 — Repository Workspace
**Priority: CRITICAL | Effort: 2–3 days**

New service: `WorkspaceManager` in `apps/api/app/services/workspace_manager.py`

Responsibilities:
- Clone the repository using GitPython + the user's PAT.
- Return the workspace path for use by downstream services.
- Clean up on completion.

New components:
```
WorkspaceManager
```

This is the foundation everything else depends on.

### Phase 3 — Full File Retrieval
**Priority: CRITICAL | Effort: 1–2 days | Depends on: Phase 2**

New utility: `FileLoader` in `packages/agents/forge_agents/file_loader.py`

Responsibilities:
- Read complete file contents from the workspace path.
- Return structured `FullFileContext` objects to the DeveloperAgent and PlannerAgent.
- Replace chunk-only context with: chunks (for relevance ranking) + full file (for editing).

Update `DeveloperAgent.develop()` to accept `full_file_contexts` alongside `retrieved_chunks`.

### Phase 4 — Patch Executor
**Priority: CRITICAL | Effort: 2–3 days | Depends on: Phase 2 + Phase 3**

New service: `PatchExecutor` in `apps/api/app/services/patch_executor.py`

Responsibilities:
- Apply `CodeChange.patch` (unified diff) to the file in the workspace.
- Validate that the patch applied cleanly.
- On failure: return the full file + broken patch to the caller for LLM retry.
- Track which files were successfully modified.

Functions:
```python
apply_patch(workspace_path, code_change) -> PatchResult
rollback_all(workspace_path)
```

### Phase 5 — Git Operations
**Priority: CRITICAL | Effort: 2–3 days | Depends on: Phase 4**

New service: `GitService` in `apps/api/app/services/git_service.py`

Responsibilities:
- Create a new branch: `forge/issue-{number}-{slug}`.
- Stage modified files.
- Commit with a structured message.
- Push to the remote using the user's PAT.

Functions:
```python
create_branch(workspace_path, branch_name)
commit_changes(workspace_path, message)
push_branch(workspace_path, remote_url, pat)
```

### Phase 6 — GitHub Pull Request Creation
**Priority: CRITICAL | Effort: 1–2 days | Depends on: Phase 5**

New service: `GitHubPRService` in `apps/api/app/services/github_pr_service.py`

Responsibilities:
- Create a real pull request via the GitHub REST API.
- Use the `PullRequestDraft` generated by the existing `PRGeneratorAgent`.
- Return the PR URL and number back to the workflow state.

Output added to `SentinelState`:
```python
pull_request_url: str | None
pull_request_number: int | None
```

### Phase 7 — Auto Repair Loop
**Priority: HIGH | Effort: 3–5 days | Depends on: Phase 4**

The `SentinelState` already has `iteration` and `max_iterations` fields.

Add a conditional edge in `graph.py`:
- After patch application, if the patch failed: route back to Developer.
- After Reviewer, if `review.approved` is False: route back to Developer.
- Stop after `max_iterations` (default: 3).

### Phase 8 — Real Validation (future)
**Priority: HIGH | Deferred until after Docker sandbox**

Run language-specific validators (HTML: `html-validate`, Python: `py_compile`, TS: `tsc --noEmit`) inside a Docker container.

Do not implement this until Phase 10 (Docker) is complete.

### Phase 9 — Real Test Execution
**Status: ✅ done for the local html-validate stack (spec 16) | Broader runners deferred**

Done: test-first authoring (`TestDesignerAgent`) + real local execution
(`SandboxRunner`: `html-validate` + DOM/content assertions) replaces the LLM-simulated
`TestAgent` in the graph, with a `tests_failed` auto-repair edge. Runs as a local
subprocess behind a swappable interface.

Still future (after Docker, Phase 10): execute `pytest`, `npm test`, `go test`, etc., and
run untrusted/deployed test code inside a Docker container.

### Phase 10 — Docker Sandbox (future)
**Priority: CRITICAL | Deferred**

All command execution (builds, tests, linters) runs inside a Docker container with:
- CPU limit: 2 cores
- Memory limit: 2 GB
- Timeout: 15 minutes
- Network: restricted (no outbound after clone)

Implement this before exposing Forge to any public traffic or untrusted repositories.

### Phase 11 — Observability (future)
OpenTelemetry traces, token usage tracking, run success/failure metrics.

---

## Execution Order (Critical Path)

```
Phase 1 (UI diffs)
    ↓
Phase 2 (WorkspaceManager)
    ↓
Phase 3 (Full File Retrieval)
    ↓
Phase 4 (PatchExecutor)
    ↓
Phase 5 (Git Operations)
    ↓
Phase 6 (GitHub PR Creation)
    ↓
Phase 7 (Auto Repair Loop)
```

Phases 8–11 follow after the above critical path is proven on HTML repositories.

---

## MVP Target Repository Profile

The end-to-end pipeline will be validated against:

- 2–3 HTML files
- Maximum 30–40 lines per file
- Issues that are simple text/attribute corrections (typos, color changes, label fixes)
- No build tools, no test runner, no dependencies

This is intentional. Prove the pipeline is real before expanding to complex codebases.

---

## PAT Storage Schema

The user's GitHub PAT must be stored on the `Repository` model.

Column: `github_pat` — encrypted string, nullable.

Set during repository connection. Required before any agent run that involves write operations (Phases 5–6).

Never return this field in any API response. Never log it.
