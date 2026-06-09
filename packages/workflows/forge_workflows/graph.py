"""Sentinel Brain LangGraph workflow definition.

Defines the multi-agent pipeline as a compiled LangGraph ``StateGraph``.
Each node is a placeholder that updates ``current_agent`` and returns state
unchanged — business logic will be injected when agents are implemented.

Graph topology::

    START
      → repo_analyzer
      → issue_analyzer
      → issue_prioritizer
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
from typing import Literal

from langgraph.graph import END, START, StateGraph

from forge_workflows.state import SentinelState, SentinelStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node names — single source of truth for string references
# ---------------------------------------------------------------------------

REPO_ANALYZER = "repo_analyzer"
ISSUE_ANALYZER = "issue_analyzer"
ISSUE_PRIORITIZER = "issue_prioritizer"
RETRIEVE_CONTEXT = "retrieve_context"
PLANNER = "planner"
DEVELOPER = "developer"
VALIDATOR = "validator"
TEST_AGENT = "test_agent"
REVIEWER = "reviewer"
PR_GENERATOR = "pr_generator"


# ---------------------------------------------------------------------------
# Placeholder node functions
# ---------------------------------------------------------------------------


async def repo_analyzer(state: SentinelState) -> dict:
    """Analyze repository structure and technology stack.

    Loads data from Postgres (repository_repo, file_repo) and calls
    the RepoAnalyzerAgent to produce a RepoContext.
    """
    logger.info("Node: %s", REPO_ANALYZER)

    import uuid
    from app.database import AsyncSessionLocal
    from app.repositories import file_repo, repository_repo
    from app.config import settings
    from forge_agents.repo_analyzer import RepoAnalyzerAgent
    from langchain_google_genai import ChatGoogleGenerativeAI

    repo_id = uuid.UUID(state.repository_id)

    async with AsyncSessionLocal() as session:
        repo = await repository_repo.get_by_id(session, repo_id)
        if not repo:
            raise ValueError(f"Repository {repo_id} not found")

        total_files, files = await file_repo.list_for_repo(session, repo_id, limit=10000)

        file_paths = [f.path for f in files]
        file_languages = {f.path: f.language for f in files}

    llm = ChatGoogleGenerativeAI(
        model=settings.brain_llm_model,
        google_api_key=settings.google_api_key,
        temperature=0.2,
    )
    agent = RepoAnalyzerAgent(llm=llm)

    repo_context = await agent.analyze(
        repo_name=repo.full_name,
        repo_description=repo.description or "",
        file_paths=file_paths,
        file_languages=file_languages,
        total_files=total_files,
    )

    return {
        "current_agent": REPO_ANALYZER,
        "status": SentinelStatus.ANALYZING_REPO,
        "repo_context": repo_context,
    }


async def issue_analyzer(state: SentinelState) -> dict:
    """Analyze open issues for the repository.

    Loads issues from Postgres (issue_repo) and calls the
    IssueAnalyzerAgent to classify each one into an IssueAnalysis.
    """
    logger.info("Node: %s", ISSUE_ANALYZER)

    import uuid
    from app.database import AsyncSessionLocal
    from app.repositories import issue_repo
    from app.config import settings
    from forge_agents.issue_analyzer import IssueAnalyzerAgent
    from langchain_google_genai import ChatGoogleGenerativeAI

    repo_id = uuid.UUID(state.repository_id)

    async with AsyncSessionLocal() as session:
        total, issues = await issue_repo.list_for_repo(
            session, repo_id, state="open", limit=200
        )

    if not issues:
        logger.warning("No open issues found for repository %s", repo_id)
        return {
            "current_agent": ISSUE_ANALYZER,
            "status": SentinelStatus.ANALYZING_ISSUES,
            "issue_analyses": [],
        }

    # Convert ORM Issue objects to plain dicts for the pure agent
    issue_dicts = [
        {
            "issue_id": str(issue.id),
            "number": issue.number,
            "title": issue.title,
            "body": issue.body or "",
            "labels": issue.labels or [],
            "state": issue.state,
        }
        for issue in issues
    ]

    llm = ChatGoogleGenerativeAI(
        model=settings.brain_llm_model,
        google_api_key=settings.google_api_key,
        temperature=0.2,
    )
    agent = IssueAnalyzerAgent(llm=llm)

    analyses = await agent.analyze(
        issues=issue_dicts,
        repo_context=state.repo_context,
    )

    return {
        "current_agent": ISSUE_ANALYZER,
        "status": SentinelStatus.ANALYZING_ISSUES,
        "issue_analyses": analyses,
    }



async def issue_prioritizer(state: SentinelState) -> dict:
    """Select the highest-priority issue to work on.

    Consumes ``state.issue_analyses`` from the prior issue_analyzer node
    and calls the IssuePrioritizerAgent to select a single issue.
    Supports ``state.target_issue_id`` to bypass LLM ranking.
    """
    logger.info("Node: %s", ISSUE_PRIORITIZER)

    from app.config import settings
    from forge_agents.issue_prioritizer import IssuePrioritizerAgent
    from langchain_google_genai import ChatGoogleGenerativeAI

    if not state.issue_analyses:
        logger.warning("No issue analyses available — cannot prioritize")
        return {
            "current_agent": ISSUE_PRIORITIZER,
            "status": SentinelStatus.PRIORITIZING,
        }

    llm = ChatGoogleGenerativeAI(
        model=settings.brain_llm_model,
        google_api_key=settings.google_api_key,
        temperature=0.2,
    )
    agent = IssuePrioritizerAgent(llm=llm)

    selected_issue = await agent.prioritize(
        issue_analyses=state.issue_analyses,
        target_issue_id=state.target_issue_id,
    )

    return {
        "current_agent": ISSUE_PRIORITIZER,
        "status": SentinelStatus.PRIORITIZING,
        "selected_issue": selected_issue,
    }


async def retrieve_context(state: SentinelState) -> dict:
    """Retrieve relevant code chunks from Qdrant.

    Embeds the selected issue text, searches the repository's Qdrant
    collection, and returns the top-k most relevant code chunks.

    Note: This is a deterministic utility node, not an LLM-powered agent.
    """
    logger.info("Node: %s", RETRIEVE_CONTEXT)

    from app.config import settings
    from forge_agents.retrieve_context import RetrieveContextAgent
    from forge_repository_analysis.embedder import CodeEmbedder
    from forge_vector_store import VectorStore

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

    collection = f"repo_{state.repository_id}"

    embedder = CodeEmbedder(settings.google_api_key, settings.embedding_model)
    vector_store = VectorStore(settings.qdrant_url, settings.qdrant_api_key or None)

    agent = RetrieveContextAgent(embedder=embedder, vector_store=vector_store)

    chunks = await agent.retrieve(
        collection=collection,
        query=query,
        limit=5,
    )

    return {
        "current_agent": RETRIEVE_CONTEXT,
        "status": SentinelStatus.RETRIEVING_CONTEXT,
        "relevant_chunks": chunks,
    }


async def planner(state: SentinelState) -> dict:
    """Create an implementation plan for the selected issue.

    Synthesizes the selected issue, repository context, and retrieved
    code chunks into a structured Plan with ordered tasks.
    """
    logger.info("Node: %s", PLANNER)

    from app.config import settings
    from forge_agents.planner import PlannerAgent
    from langchain_google_genai import ChatGoogleGenerativeAI

    if not state.selected_issue:
        logger.warning("No selected issue — cannot create plan")
        return {
            "current_agent": PLANNER,
            "status": SentinelStatus.PLANNING,
        }

    llm = ChatGoogleGenerativeAI(
        model=settings.brain_llm_model,
        google_api_key=settings.google_api_key,
        temperature=0.2,
    )
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


def developer(state: SentinelState) -> dict:
    """Generate code changes based on the plan.

    Placeholder — updates ``current_agent`` and ``status`` only.
    Real implementation will call Gemini with the plan and relevant
    code to produce ``code_changes``.  On retry iterations, it also
    receives ``validation_result`` or ``review`` feedback.
    """
    logger.info("Node: %s (iteration %d)", DEVELOPER, state.iteration)
    return {
        "current_agent": DEVELOPER,
        "status": SentinelStatus.DEVELOPING,
    }


def validator(state: SentinelState) -> dict:
    """Validate the generated code changes.

    Placeholder — updates ``current_agent`` and ``status`` only.
    Real implementation will call Gemini to check code correctness,
    consistency with the plan, and write ``validation_result``.
    """
    logger.info("Node: %s", VALIDATOR)
    return {
        "current_agent": VALIDATOR,
        "status": SentinelStatus.VALIDATING,
    }


def test_agent(state: SentinelState) -> dict:
    """Generate test cases for the code changes.

    Placeholder — updates ``current_agent`` and ``status`` only.
    Real implementation will call Gemini to produce test cases
    and write ``test_results``.
    """
    logger.info("Node: %s", TEST_AGENT)
    return {
        "current_agent": TEST_AGENT,
        "status": SentinelStatus.TESTING,
    }


def reviewer(state: SentinelState) -> dict:
    """Review the code changes holistically.

    Placeholder — updates ``current_agent`` and ``status`` only.
    Real implementation will call Gemini to perform a code review
    and write ``review`` with approval/rejection and suggestions.
    """
    logger.info("Node: %s", REVIEWER)
    return {
        "current_agent": REVIEWER,
        "status": SentinelStatus.REVIEWING,
    }


def pr_generator(state: SentinelState) -> dict:
    """Generate pull request metadata.

    Placeholder — updates ``current_agent`` and ``status`` only.
    Real implementation will call Gemini to produce a PR title,
    body, and branch name, then write ``pull_request_draft``.
    """
    logger.info("Node: %s", PR_GENERATOR)
    return {
        "current_agent": PR_GENERATOR,
        "status": SentinelStatus.GENERATING_PR,
    }


# ---------------------------------------------------------------------------
# Conditional routing functions
# ---------------------------------------------------------------------------


def route_after_validator(state: SentinelState) -> Literal["developer", "test_agent"]:
    """Decide whether to retry development or proceed to testing.

    Routes back to ``developer`` if:
        - ``validation_result`` exists AND ``passed`` is False
        - AND ``iteration`` < ``max_iterations``

    Otherwise proceeds to ``test_agent``.
    """
    vr = state.validation_result
    if vr is not None and not vr.passed and state.iteration < state.max_iterations:
        logger.info("Validation failed (iteration %d) — routing back to developer", state.iteration)
        return DEVELOPER
    return TEST_AGENT


def route_after_reviewer(state: SentinelState) -> Literal["developer", "pr_generator"]:
    """Decide whether to retry development or proceed to PR generation.

    Routes back to ``developer`` if:
        - ``review`` exists AND ``approved`` is False
        - AND ``iteration`` < ``max_iterations``

    Otherwise proceeds to ``pr_generator``.
    """
    rev = state.review
    if rev is not None and not rev.approved and state.iteration < state.max_iterations:
        logger.info("Review rejected (iteration %d) — routing back to developer", state.iteration)
        return DEVELOPER
    return PR_GENERATOR


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def build_graph() -> StateGraph:
    """Build and return the Sentinel Brain LangGraph workflow.

    Returns a compiled ``StateGraph`` with all nodes wired and
    conditional edges for the validator→developer and reviewer→developer
    feedback loops.
    """
    graph = StateGraph(SentinelState)

    # --- Register nodes ---
    graph.add_node(REPO_ANALYZER, repo_analyzer)
    graph.add_node(ISSUE_ANALYZER, issue_analyzer)
    graph.add_node(ISSUE_PRIORITIZER, issue_prioritizer)
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
    graph.add_edge(ISSUE_ANALYZER, ISSUE_PRIORITIZER)
    graph.add_edge(ISSUE_PRIORITIZER, RETRIEVE_CONTEXT)
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
