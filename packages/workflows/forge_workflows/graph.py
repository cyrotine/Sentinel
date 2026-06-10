"""Sentinel Brain LangGraph workflow definition.

Defines the multi-agent pipeline as a compiled LangGraph ``StateGraph``.

This module is **application-agnostic**: it imports nothing from ``app.*`` and
never touches the database or constructs LLM clients.  All dependencies
(``llm``, ``embedder``, ``vector_store``) are injected via :func:`build_graph`,
and all repository data is read from pre-loaded ``state.inputs`` fields populated
by the application's ``BrainService`` before the graph is invoked.

Graph topology::

    START
      → repo_analyzer
      → issue_analyzer   (filters to user-selected issue, promotes to selected_issue)
      → retrieve_context
      → planner
      → developer
      → validator ──→ (route_after_validator)
      │                  ├─ valid or max retries → test_agent
      │                  └─ invalid              → developer
      → test_agent
      → reviewer ───→ (route_after_reviewer)
      │                  ├─ approved or max retries → pr_generator
      │                  └─ rejected                → developer
      → pr_generator
      → END
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

from langgraph.graph import END, START, StateGraph

from forge_agents.developer import DeveloperAgent
from forge_agents.issue_analyzer import IssueAnalyzerAgent
from forge_agents.planner import PlannerAgent
from forge_agents.pr_generator import PRGeneratorAgent
from forge_agents.repo_analyzer import RepoAnalyzerAgent
from forge_agents.retrieve_context import RetrieveContextAgent
from forge_agents.reviewer import ReviewerAgent
from forge_agents.test_agent import TestAgent
from forge_agents.validator import ValidatorAgent
from forge_workflows.state import IssueAnalysis, SelectedIssue, SentinelState, SentinelStatus, ValidationResult

if TYPE_CHECKING:
    from forge_repository_analysis.embedder import CodeEmbedder
    from forge_vector_store.store import VectorStore
    from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node names — single source of truth for string references
# ---------------------------------------------------------------------------

REPO_ANALYZER = "repo_analyzer"
ISSUE_ANALYZER = "issue_analyzer"
RETRIEVE_CONTEXT = "retrieve_context"
PLANNER = "planner"
DEVELOPER = "developer"
VALIDATOR = "validator"
TEST_AGENT = "test_agent"
REVIEWER = "reviewer"
PR_GENERATOR = "pr_generator"


# ---------------------------------------------------------------------------
# Conditional routing functions (pure — no injected dependencies)
# ---------------------------------------------------------------------------


def route_after_validator(state: SentinelState) -> Literal["developer", "test_agent"]:
    """Decide whether to retry development or proceed to testing.

    Routes back to ``developer`` if validation failed and the iteration budget
    is not exhausted; otherwise proceeds to ``test_agent``.
    """
    vr = state.validation_result
    if vr is not None and not vr.passed and state.iteration < state.max_iterations:
        logger.info("Validation failed (iteration %d) — routing back to developer", state.iteration)
        return DEVELOPER
    return TEST_AGENT


def route_after_reviewer(state: SentinelState) -> Literal["developer", "pr_generator"]:
    """Decide whether to retry development or proceed to PR generation.

    Routes back to ``developer`` if the review was rejected and the iteration
    budget is not exhausted; otherwise proceeds to ``pr_generator``.
    """
    rev = state.review
    if rev is not None and not rev.approved and state.iteration < state.max_iterations:
        logger.info("Review rejected (iteration %d) — routing back to developer", state.iteration)
        return DEVELOPER
    return PR_GENERATOR


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def _estimate_complexity(analysis: IssueAnalysis) -> str:
    area_count = len(analysis.affected_areas)
    if analysis.issue_type in ("refactor", "feature") and area_count > 3:
        return "high"
    if area_count > 1 or analysis.issue_type == "feature":
        return "medium"
    return "low"


def build_graph(
    llm: BaseChatModel,
    embedder: CodeEmbedder,
    vector_store: VectorStore,
) -> StateGraph:
    """Build the Sentinel Brain LangGraph workflow with injected dependencies.

    Args:
        llm: A LangChain chat model shared by all LLM-powered nodes.
        embedder: Code embedder used by the ``retrieve_context`` node.
        vector_store: Qdrant-backed store used by the ``retrieve_context`` node.

    Returns:
        An uncompiled ``StateGraph`` with all nodes wired and conditional edges
        for the validator→developer and reviewer→developer feedback loops.
        Call ``.compile()`` on the result before invoking it.
    """

    # --- Nodes (closures over the injected dependencies) ---

    async def repo_analyzer(state: SentinelState) -> dict:
        """Analyze repository structure and technology stack from pre-loaded data."""
        logger.info("Node: %s", REPO_ANALYZER)
        agent = RepoAnalyzerAgent(llm=llm)
        repo_context = await agent.analyze(
            repo_name=state.inputs.repo_name,
            repo_description=state.inputs.repo_description,
            file_paths=state.inputs.file_paths,
            file_languages=state.inputs.file_languages,
            total_files=state.inputs.total_files,
        )
        return {
            "current_agent": REPO_ANALYZER,
            "status": SentinelStatus.ANALYZING_REPO,
            "repo_context": repo_context,
        }

    async def issue_analyzer(state: SentinelState) -> dict:
        """Filter to the user-selected issue, classify it, and promote to selected_issue."""
        logger.info("Node: %s", ISSUE_ANALYZER)

        if not state.target_issue_id:
            raise ValueError(
                "target_issue_id is required — select an issue before starting a run"
            )

        issues_to_analyze = [
            i for i in state.inputs.raw_issues if i["issue_id"] == state.target_issue_id
        ]
        if not issues_to_analyze:
            raise ValueError(
                f"target_issue_id {state.target_issue_id!r} not found in raw_issues"
            )

        logger.info("Targeted analysis: issue_id=%s only", state.target_issue_id)
        agent = IssueAnalyzerAgent(llm=llm)
        analyses = await agent.analyze(
            issues=issues_to_analyze,
            repo_context=state.repo_context,
        )

        analysis = analyses[0]
        selected = SelectedIssue(
            issue_id=analysis.issue_id,
            number=analysis.number,
            title=analysis.title,
            body=analysis.body,
            reasoning=(
                f"User-selected issue #{analysis.number}: "
                f"{analysis.issue_type}/{analysis.severity}."
            ),
            estimated_complexity=_estimate_complexity(analysis),
        )

        return {
            "current_agent": ISSUE_ANALYZER,
            "status": SentinelStatus.ANALYZING_ISSUES,
            "issue_analyses": analyses,
            "selected_issue": selected,
        }

    async def retrieve_context(state: SentinelState) -> dict:
        """Retrieve relevant code chunks from Qdrant (deterministic utility node)."""
        logger.info("Node: %s", RETRIEVE_CONTEXT)

        if not state.selected_issue:
            logger.warning("No selected issue — skipping context retrieval")
            return {
                "current_agent": RETRIEVE_CONTEXT,
                "status": SentinelStatus.RETRIEVING_CONTEXT,
                "relevant_chunks": [],
            }

        # Build semantic search query from issue title + body
        query_parts = [state.selected_issue.title]
        if state.selected_issue.body:
            query_parts.append(state.selected_issue.body)
        query = " ".join(query_parts)

        collection = state.inputs.collection_name or f"repo_{state.repository_id}"

        agent = RetrieveContextAgent(embedder=embedder, vector_store=vector_store)
        chunks = await agent.retrieve(collection=collection, query=query, limit=5)

        return {
            "current_agent": RETRIEVE_CONTEXT,
            "status": SentinelStatus.RETRIEVING_CONTEXT,
            "relevant_chunks": chunks,
        }

    async def planner(state: SentinelState) -> dict:
        """Create an implementation plan for the selected issue."""
        logger.info("Node: %s", PLANNER)

        if not state.selected_issue:
            logger.warning("No selected issue — cannot create plan")
            return {
                "current_agent": PLANNER,
                "status": SentinelStatus.PLANNING,
            }

        agent = PlannerAgent(llm=llm)
        plan = await agent.plan(
            selected_issue=state.selected_issue,
            repo_context=state.repo_context,
            retrieved_chunks=state.relevant_chunks,
        )
        return {
            "current_agent": PLANNER,
            "status": SentinelStatus.PLANNING,
            "plan": plan,
        }

    async def developer(state: SentinelState) -> dict:
        """Generate code changes based on the plan.

        On retry iterations (re-entered from the validator or reviewer feedback
        loop), it increments ``iteration`` so the loops terminate at
        ``max_iterations`` rather than only at LangGraph's recursion limit.
        """
        logger.info("Node: %s (iteration %d)", DEVELOPER, state.iteration)

        if not state.plan:
            logger.warning("No plan available — cannot generate code changes")
            return {
                "current_agent": DEVELOPER,
                "status": SentinelStatus.DEVELOPING,
                "iteration": state.iteration + 1,
            }

        agent = DeveloperAgent(llm=llm)
        code_changes = await agent.develop(
            plan=state.plan,
            selected_issue=state.selected_issue,
            repo_context=state.repo_context,
            retrieved_chunks=state.relevant_chunks,
        )
        return {
            "current_agent": DEVELOPER,
            "status": SentinelStatus.DEVELOPING,
            "code_changes": code_changes,
            "iteration": state.iteration + 1,
        }

    async def validator(state: SentinelState) -> dict:
        """Validate the generated code changes."""
        logger.info("Node: %s", VALIDATOR)

        if not state.code_changes:
            logger.warning("No code changes to validate")
            return {
                "current_agent": VALIDATOR,
                "status": SentinelStatus.VALIDATING,
                "validation_result": ValidationResult(
                    passed=False,
                    issues=["No code changes were generated."],
                    suggestions=["Re-run the developer agent."],
                ),
            }

        agent = ValidatorAgent(llm=llm)
        validation_result = await agent.validate(
            code_changes=state.code_changes,
            plan=state.plan,
            selected_issue=state.selected_issue,
            repo_context=state.repo_context,
            retrieved_chunks=state.relevant_chunks,
        )
        return {
            "current_agent": VALIDATOR,
            "status": SentinelStatus.VALIDATING,
            "validation_result": validation_result,
        }

    async def test_agent(state: SentinelState) -> dict:
        """Generate simulated tests for the code changes."""
        logger.info("Node: %s", TEST_AGENT)

        agent = TestAgent(llm=llm)
        test_results = await agent.test(
            code_changes=state.code_changes,
            plan=state.plan,
            selected_issue=state.selected_issue,
            repo_context=state.repo_context,
            validation_result=state.validation_result,
        )
        return {
            "current_agent": TEST_AGENT,
            "status": SentinelStatus.TESTING,
            "test_results": test_results,
        }

    async def reviewer(state: SentinelState) -> dict:
        """Review the code changes holistically."""
        logger.info("Node: %s", REVIEWER)

        agent = ReviewerAgent(llm=llm)
        review = await agent.review(
            code_changes=state.code_changes,
            plan=state.plan,
            selected_issue=state.selected_issue,
            repo_context=state.repo_context,
            validation_result=state.validation_result,
            test_results=state.test_results,
        )
        return {
            "current_agent": REVIEWER,
            "status": SentinelStatus.REVIEWING,
            "review": review,
        }

    async def pr_generator(state: SentinelState) -> dict:
        """Generate pull request metadata."""
        logger.info("Node: %s", PR_GENERATOR)

        agent = PRGeneratorAgent(llm=llm)
        draft = await agent.generate_pr(
            code_changes=state.code_changes,
            plan=state.plan,
            selected_issue=state.selected_issue,
            repo_context=state.repo_context,
            validation_result=state.validation_result,
            test_results=state.test_results,
            review=state.review,
        )
        return {
            "current_agent": PR_GENERATOR,
            "status": SentinelStatus.GENERATING_PR,
            "pull_request_draft": draft,
        }

    # --- Assemble the graph ---

    graph = StateGraph(SentinelState)

    graph.add_node(REPO_ANALYZER, repo_analyzer)
    graph.add_node(ISSUE_ANALYZER, issue_analyzer)
    graph.add_node(RETRIEVE_CONTEXT, retrieve_context)
    graph.add_node(PLANNER, planner)
    graph.add_node(DEVELOPER, developer)
    graph.add_node(VALIDATOR, validator)
    graph.add_node(TEST_AGENT, test_agent)
    graph.add_node(REVIEWER, reviewer)
    graph.add_node(PR_GENERATOR, pr_generator)

    # --- Linear edges ---
    graph.add_edge(START, REPO_ANALYZER)
    graph.add_edge(REPO_ANALYZER, ISSUE_ANALYZER)
    graph.add_edge(ISSUE_ANALYZER, RETRIEVE_CONTEXT)
    graph.add_edge(RETRIEVE_CONTEXT, PLANNER)
    graph.add_edge(PLANNER, DEVELOPER)

    # --- Conditional: validator decides retry or proceed ---
    graph.add_edge(DEVELOPER, VALIDATOR)
    graph.add_conditional_edges(
        VALIDATOR,
        route_after_validator,
        {DEVELOPER: DEVELOPER, TEST_AGENT: TEST_AGENT},
    )

    # --- Conditional: reviewer decides retry or proceed ---
    graph.add_edge(TEST_AGENT, REVIEWER)
    graph.add_conditional_edges(
        REVIEWER,
        route_after_reviewer,
        {DEVELOPER: DEVELOPER, PR_GENERATOR: PR_GENERATOR},
    )

    # --- Terminal ---
    graph.add_edge(PR_GENERATOR, END)

    return graph