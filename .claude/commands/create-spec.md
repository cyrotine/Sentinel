---

description: Create a feature specification and implementation branch for Forge
argument-hint: Feature number and feature name e.g. 03 issue-analyzer-agent
allowed-tools: Read, Write, Glob, Bash(git:*)
---------------------------------------------

You are a senior AI systems engineer building Forge — an Autonomous Multi-Agent Open Source Engineer.

Always follow the rules in CLAUDE.md.

User input: $ARGUMENTS

---

## Step 1 — Check Working Directory

Run:

git status

If there are:

* unstaged changes
* untracked files
* uncommitted changes

STOP immediately.

Tell the user to commit or stash changes before continuing.

Do not proceed until the repository is clean.

---

## Step 2 — Parse Arguments

Extract:

### feature_number

Zero-padded:

1 → 01
9 → 09
10 → 10

### feature_title

Human-readable title.

Examples:

Issue Analyzer Agent
Repository Knowledge Graph
Developer Agent
Execution Timeline

### feature_slug

Lowercase kebab-case.

Examples:

issue-analyzer-agent
repository-knowledge-graph
developer-agent

### branch_name

feature/<feature_slug>

---

## Step 3 — Verify Branch Availability

Run:

git branch

If branch already exists:

Append suffix:

feature/issue-analyzer-agent-01
feature/issue-analyzer-agent-02

etc.

---

## Step 4 — Update Main

Run:

git checkout main

git pull origin main

---

## Step 5 — Create Feature Branch

Run:

git checkout -b <branch_name>

---

## Step 6 — Research Existing System

Read:

CLAUDE.md

apps/web/

apps/api/

packages/agents/

packages/workflows/

packages/shared/

packages/vector-store/

packages/repository-analysis/

.claude/specs/

---

Verify feature is not already implemented.

If feature already exists:

Warn user and stop.

---

## Step 7 — Generate Spec

Create a specification with the following structure.

# Spec: <feature_title>

## Overview

Describe:

* What the feature does
* Why it exists
* How it contributes to autonomous software engineering

---

## Depends On

List required previous features.

If none:

No dependencies.

---

## User Story

Describe:

Who uses this feature.

Example:

"As a repository owner, I want Forge to automatically classify issues so that higher-impact issues can be prioritized."

---

## Agent Changes

List:

### Create

New agents

Example:

IssueAnalyzerAgent

Responsibilities:

* classify issues
* estimate severity
* estimate confidence

### Modify

Existing agents affected.

If none:

No agent changes.

---

## Workflow Changes

Describe LangGraph modifications.

Include:

### Inputs

### Outputs

### State Changes

### Graph Nodes

### Graph Edges

If none:

No workflow changes.

---

## Database Changes

PostgreSQL tables affected.

For each:

### Create

Table

Columns

Relationships

### Modify

Existing tables

If none:

No database changes.

---

## Retrieval Changes

Vector database modifications.

Examples:

* New embeddings
* New collections
* Retrieval logic

If none:

No retrieval changes.

---

## API Changes

New endpoints.

Example:

POST /api/issues/analyze

GET /api/issues/:id

Include:

Request schema

Response schema

---

## Frontend Changes

Pages:

Components:

Visualizations:

Dashboard modules:

State management:

---

## Files To Modify

List every modified file.

---

## Files To Create

List every new file.

---

## New Packages

List required packages.

If package approval needed:

Flag clearly.

If none:

No new packages.

---

## Implementation Rules

Always include:

* TypeScript strict mode
* No any without justification
* Use Pydantic schemas for backend contracts
* All LangGraph state must be typed
* No raw dictionaries between workflow nodes
* No business logic in API routes
* Use repository/service pattern
* Targeted edits only
* Maintain existing architecture
* Docker sandbox for code execution
* Retrieval must use vector database, never full repository context

---

## Definition Of Done

Provide a checklist.

Every item must be testable.

Example:

* [ ] Repository can be analyzed successfully
* [ ] Issue classification returns severity
* [ ] Confidence score generated
* [ ] Workflow state updated correctly
* [ ] API endpoint returns valid schema
* [ ] Dashboard displays analysis result

---

## Architecture Impact

Describe:

* affected systems
* dependencies introduced
* scalability concerns
* future extensions

---

## Risks

List:

* technical risks
* performance risks
* LLM failure modes
* mitigation strategies

---

## Step 8 — Save Spec

Save:

.claude/specs/<feature_number>-<feature_slug>.md

---

## Step 9 — Report

Print:

Branch:    <branch_name>
Spec file: .claude/specs/<feature_number>-<feature_slug>.md
Title:     <feature_title>

Then tell the user:

Review the spec before implementation.

Verify:

* agent contracts
* workflow state schema
* API schemas
* database changes

before writing code.
