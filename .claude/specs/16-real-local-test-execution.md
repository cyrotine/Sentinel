# Spec: Real Local Test Execution

## Overview

Today the `TestAgent` (`packages/agents/forge_agents/test_agent.py`) is a pure LLM
class: it *invents* test cases and *simulates* their pass/fail outcome through
reasoning. Nothing is actually executed. This spec replaces that simulation with
**real, test-first verification** for the static-HTML MVP target:

1. **Test-first authoring.** A new `TestDesignerAgent` runs *after the planner and
   before the developer*. It reads the issue's acceptance criteria, the plan, and the
   full files, and emits **concrete, executable check artifacts** (an `html-validate`
   configuration plus structured DOM/content assertions) — written blind to the
   implementation. This is true TDD: the tests are defined independently of the code
   that will satisfy them.

2. **Real execution.** The rewritten `test_agent` node stops reasoning. After patches
   are applied to the workspace, it writes the test artifacts into that workspace and
   executes the real `html-validate` command via a new `SandboxRunner`, parsing the
   actual exit code and JSON output into `TestResult`s.

3. **Repair on red.** Failing tests feed back into the existing auto-repair loop so the
   developer regenerates code to make the tests pass, bounded by `max_iterations`.

This advances Forge from "Decide/Act with simulated verification" to genuine
**Act + Verify**, directly serving the autonomy goal in CLAUDE.md: the system now
produces evidence its changes are correct rather than asserting they are.

**Scope boundary (locked by user decision):** execution runs **locally only** against
the developer's machine. No Railway/Vercel deployment work is in scope. The first and
only runner targets the `html-validate` stack, matching the 2–3 file static-HTML MVP
profile. The `SandboxRunner` is built behind an interface so a deployed/managed sandbox
can be swapped in later without touching the graph or agents.

---

## Depends On

- **08 — Full File Retrieval** (`full_file_contexts` on state; `TestDesignerAgent`
  consumes them).
- **09 — Patch Executor** (`apply_patches` node lands code on disk before tests run).
- **12 — Auto Repair Loop** (`iteration`/`max_iterations`, `RepairContext`,
  `_build_repair_context`; this spec extends them with a test-failure trigger).

---

## User Story

> As a repository owner, I want Forge to **write real tests for an issue before it
> writes the code, then actually run those tests against its own changes**, so that the
> pull request it drafts is backed by passing checks instead of an LLM's guess that the
> change "looks correct."

---

## Agent Changes

### Create

**`TestDesignerAgent`** (`packages/agents/forge_agents/test_designer.py`)

Responsibilities:

- Read `selected_issue`, `plan`, `repo_context`, and `full_file_contexts`.
- Derive acceptance criteria from the issue + the planner's `tests_needed`
  (currently folded into `Plan.approach_reasoning` text — see Workflow Changes).
- Emit a list of typed `TestSpec` objects: an `html-validate` ruleset/config and/or
  structured DOM/content assertions, each tied to a named acceptance criterion.
- Author tests **without** seeing the developer's patch (it runs before the developer).
- Deterministic fallback when the LLM is unavailable (mirror the existing agents'
  fallback pattern).

### Modify

**`TestAgent`** (`packages/agents/forge_agents/test_agent.py`) — rewritten:

- Remove LLM reasoning (`_build_prompt`, `_parse_llm_response`, `_build_test_results`)
  and the `_fallback_test` heuristic simulation.
- New contract: accept `test_specs` + `workspace_path`, write the specs into the
  workspace, invoke `SandboxRunner`, and map real output → `list[TestResult]`
  (`name`, `passed`, `output`=runner stdout/stderr, `error`, `exit_code`, `spec_id`).
- No LLM dependency remains on this node (it becomes deterministic execution).

**`PlannerAgent`** (`packages/agents/forge_agents/planner.py`) — minor:

- `tests_needed` is already produced (parsed at `planner.py:260`) but is flattened into
  `approach_reasoning` text. Surface it as a structured field on `Plan` so the
  `TestDesignerAgent` can consume acceptance criteria without re-parsing prose.

**`ReviewerAgent` / `PRGeneratorAgent`** — no contract change; they already receive
`test_results` and will now see real outcomes. Verify their prompts read sensibly with
real runner output (no code change expected).

---

## Workflow Changes

### Inputs

- `TestDesignerAgent`: `selected_issue`, `plan` (incl. structured `tests_needed`),
  `repo_context`, `full_file_contexts`.
- `test_agent` node: `test_specs`, `workspace_path`, `code_changes`.

### Outputs

- `test_designer` node → `state.test_specs: list[TestSpec]`.
- `test_agent` node → `state.test_results: list[TestResult]` (now real).

### State Changes (`packages/workflows/forge_workflows/state.py`)

- **New** `TestSpec(BaseModel)`: `id`, `name`, `acceptance_criterion`, `target_file`,
  `framework` (literal `"html-validate"` for now), `config_content` and/or
  `assertions: list[...]`.
- **New** field `SentinelState.test_specs: list[TestSpec] = []`.
- **Extend** `TestResult`: add `spec_id: str | None` and `exit_code: int | None`.
- **Extend** `Plan`: add `tests_needed: list[str]` (structured, replacing prose-only).
- **Extend** `RepairContext`: add `test_failures: list[str]`; trigger value
  `"tests_failed"`. Update `_build_repair_context` in `graph.py` to populate it from
  failed `test_results`.
- **New** `SentinelStatus` value if desired: `DESIGNING_TESTS = "designing_tests"`.

### Graph Nodes (`packages/workflows/forge_workflows/graph.py`)

- Add `TEST_DESIGNER = "test_designer"` node constant + `test_designer` async node.
- Rewrite the `test_agent` node body to call `SandboxRunner` (via
  `asyncio.to_thread`) instead of the LLM `TestAgent.test()`.

### Graph Edges

- Replace `PLANNER → DEVELOPER` with `PLANNER → TEST_DESIGNER → DEVELOPER`.
- Add `route_after_test_agent(state) -> "developer" | "reviewer"` conditional
  (mirror of `route_after_validator`): route back to `developer` when any test failed
  and `iteration < max_iterations`, else proceed to `reviewer`.
- Replace the static `TEST_AGENT → REVIEWER` edge with the conditional above.

---

## Database Changes

No new tables. `agent_runs.result` is schemaless JSON populated from the
`_RESULT_FIELDS` tuple in `brain_service.py`.

### Modify

- Add `"test_specs"` to `_RESULT_FIELDS` (`brain_service.py:34`) so designed tests are
  surfaced live like every other agent output.
- Add `test_specs: list[dict] = []` to `AgentRunResult`
  (`apps/api/app/schemas/agent_run.py:33`).

---

## Retrieval Changes

No retrieval changes. The `TestDesignerAgent` reuses `full_file_contexts` already
loaded by the `load_full_files` node; it does not query Qdrant.

---

## API Changes

No new endpoints. The existing agent-run read path serializes the extended
`AgentRunResult` (now including `test_specs` and richer `test_results`). Verify the
response schema validates the new fields.

---

## Frontend Changes

Pages: Execution Timeline / Agent Center (the existing agent-run detail view).

Components:
- `apps/web/src/components/agents/agent-run-detail.tsx` — render a **Tests** section:
  the designed `test_specs` and, after execution, real `test_results` with pass/fail
  badges and a collapsible raw-output (stdout/stderr) panel. Replace the prior
  simulated-string display.

Visualizations: pass/fail badges per test; overall red/green run summary.

State management: none new — data arrives through the existing agent-run polling/stream.

Types:
- `packages/shared/src/types/index.ts` — add `TestSpec`, extend `TestResult` with
  `spec_id`/`exit_code` (keep `packages/shared/dist` in sync via the build).
- `apps/web/src/lib/api.ts` — surface the new fields in the run result type.

---

## Files To Modify

- `packages/workflows/forge_workflows/state.py` — `TestSpec`, `Plan.tests_needed`,
  `TestResult` extensions, `RepairContext.test_failures`, `SentinelState.test_specs`,
  `SentinelStatus.DESIGNING_TESTS`.
- `packages/workflows/forge_workflows/graph.py` — new node, rewired edges,
  `route_after_test_agent`, `_build_repair_context` update, `test_agent` node rewrite.
- `packages/agents/forge_agents/test_agent.py` — rewrite to execute via `SandboxRunner`.
- `packages/agents/forge_agents/planner.py` — emit structured `tests_needed`.
- `packages/agents/forge_agents/__init__.py` — export `TestDesignerAgent`.
- `apps/api/app/services/brain_service.py` — add `test_specs` to `_RESULT_FIELDS`.
- `apps/api/app/schemas/agent_run.py` — add `test_specs` to `AgentRunResult`.
- `packages/shared/src/types/index.ts` — `TestSpec` + `TestResult` fields.
- `apps/web/src/lib/api.ts` — run-result typing.
- `apps/web/src/components/agents/agent-run-detail.tsx` — Tests UI section.

## Files To Create

- `packages/agents/forge_agents/test_designer.py` — `TestDesignerAgent`.
- `apps/api/app/services/sandbox_runner.py` — `SandboxRunner` service (local execution
  of `html-validate` against the workspace, behind a swappable interface).
- Tests: `packages/agents/tests/test_test_designer.py`,
  `apps/api/tests/test_sandbox_runner.py` (follow existing test layout).

---

## New Packages

- **`html-validate`** (npm) — the real test runner. Run locally via `npx html-validate`
  (no Docker required for local-only scope) or a thin local Docker image. **Flag for
  approval:** this is the one external execution dependency introduced.
- No new Python packages — `SandboxRunner` shells out via `subprocess`/`asyncio`.

---

## Implementation Rules

- TypeScript strict mode; no `any` without justification.
- Pydantic schemas for all backend contracts (`TestSpec`, `TestResult`).
- All LangGraph state typed; no raw dictionaries between nodes (`TestSpec` flows as a
  model, never a dict).
- No business logic in API routes; keep execution in the `SandboxRunner` service
  (service/repository pattern).
- Targeted edits only; preserve existing architecture and the injected-dependency
  pattern in `build_graph`.
- The graph stays application-agnostic: `SandboxRunner` is invoked from the node
  closure, not imported into pure routing functions.
- **Never** expose the GitHub PAT to the runner — execution happens post-graph-state
  and the runner only ever sees workspace files, never secrets.
- **Sandbox/execution safety:** untrusted, LLM-authored test artifacts are executed.
  For local scope, run with a hard timeout and no extra privileges. The
  `SandboxRunner` interface MUST keep a Docker/managed-sandbox backend swappable for
  when this is deployed (CLAUDE.md Phase 10).
- Retrieval continues to use the vector DB / pre-loaded file contexts, never full repo
  context.

---

## Definition Of Done

- [ ] `TestDesignerAgent` produces ≥1 typed `TestSpec` for a static-HTML issue, before
      the developer runs.
- [ ] `test_specs` appears in `SentinelState` and in `agent_runs.result`.
- [ ] `PLANNER → TEST_DESIGNER → DEVELOPER` ordering holds in the compiled graph.
- [ ] `SandboxRunner` executes `html-validate` against the patched workspace and
      returns real exit code + output.
- [ ] `test_agent` node produces `TestResult`s with real `passed`/`exit_code`/`spec_id`
      — no LLM call on this node.
- [ ] A deliberately wrong patch yields a **failing** `TestResult` (red), proving
      execution is real, not simulated.
- [ ] On a failing test with iterations remaining, the graph routes back to `developer`
      and `RepairContext.test_failures` is populated.
- [ ] The run terminates at `max_iterations` even if tests keep failing (no infinite
      loop; recursion backstop untouched).
- [ ] Agent-run detail UI shows designed specs + real pass/fail badges + raw output.
- [ ] Existing pipeline (issue → plan → code → PR draft) still completes end-to-end on
      the MVP HTML target.

---

## Architecture Impact

- **Affected systems:** workflow graph (new node + conditional edge), agents package
  (new agent + rewritten agent), API serialization, shared types, web UI.
- **Dependencies introduced:** `html-validate` (npm) as an executable test runner; a
  new `SandboxRunner` service boundary.
- **Scalability concerns:** real execution adds wall-clock latency and CPU per run;
  bounded by the per-run timeout and `max_iterations`. Local-only for now, so no
  multi-tenant concurrency concerns yet.
- **Future extensions:** the `TestSpec.framework` field and the `SandboxRunner`
  interface generalize to `pytest`/`jest` and to a deployed Docker/Firecracker sandbox
  (CLAUDE.md Phases 9–10) without graph changes — only a new runner backend.

---

## Risks

- **Executing untrusted code (technical/security):** test artifacts are LLM-authored.
  *Mitigation:* local scope only; hard timeout; no privileges; interface ready for full
  sandbox before any deployment. This spec intentionally reverses the "Test Execution —
  deferred" decision in CLAUDE.md **for local html-validate only** — update that
  section and the Phase 9 status when implementing so docs and code do not drift.
- **TDD deadlock (LLM failure mode):** the designer may write tests the developer can
  never satisfy within `max_iterations`. *Mitigation:* iteration cap + clear test
  output fed back via `RepairContext`; surface the red run in the PR draft rather than
  blocking.
- **Flaky/over-strict html-validate rules (performance/correctness):** overly aggressive
  rulesets fail valid HTML. *Mitigation:* designer emits a minimal ruleset scoped to the
  acceptance criterion; deterministic fallback to a conservative default config.
- **Parsing runner output (technical):** html-validate JSON shape changes between
  versions. *Mitigation:* pin the version; defensive parsing with a clear error
  `TestResult` on unexpected output.
- **Schema drift (technical):** `packages/shared/dist` can lag `src`. *Mitigation:*
  rebuild shared types as part of the change; CI/build check.