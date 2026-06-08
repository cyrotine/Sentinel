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
