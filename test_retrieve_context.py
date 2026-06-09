"""End-to-end test of the retrieve_context node against real ingested data.

Tests:
  1. repo_analyzer produces RepoContext (prerequisite)
  2. issue_analyzer classifies issues (prerequisite)
  3. issue_prioritizer selects the best issue (prerequisite)
  4. retrieve_context embeds the issue and searches Qdrant
  5. RetrievedChunk outputs are populated correctly
  6. State transitions: PENDING -> ... -> RETRIEVING_CONTEXT -> COMPLETED

Repository: 70cc7b50-ca9d-41ef-be4c-bb56f1be9a82 (cyrotine/TempRepo)
Expected: index.html should be the top result (contains "Hello World" text styling)
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.abspath("apps/api"))

from forge_workflows.state import (
    SentinelState,
    SentinelStatus,
    RetrievedChunk,
)
from forge_workflows.graph import (
    repo_analyzer,
    issue_analyzer,
    issue_prioritizer,
    retrieve_context,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("test")

REPO_ID = "70cc7b50-ca9d-41ef-be4c-bb56f1be9a82"


async def main() -> None:
    # ---------------------------------------------------------------
    # Phase 1: Initial state
    # ---------------------------------------------------------------
    state = SentinelState(repository_id=REPO_ID)

    print("\n" + "=" * 60)
    print("PHASE 1: Initial State")
    print("=" * 60)
    print(f"  status:           {state.status}")
    print(f"  relevant_chunks:  {len(state.relevant_chunks)}")
    assert state.status == SentinelStatus.PENDING
    assert state.relevant_chunks == []
    print("  [PASS] Initial state is PENDING, no chunks")

    # ---------------------------------------------------------------
    # Phase 2: Run repo_analyzer
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PHASE 2: Run repo_analyzer")
    print("=" * 60)

    result = await repo_analyzer(state)
    state = state.model_copy(update=result)
    assert state.status == SentinelStatus.ANALYZING_REPO
    print(f"  repo: {state.repo_context.repository_name}")
    print("  [PASS] repo_analyzer completed")

    # ---------------------------------------------------------------
    # Phase 3: Run issue_analyzer
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PHASE 3: Run issue_analyzer")
    print("=" * 60)

    result = await issue_analyzer(state)
    state = state.model_copy(update=result)
    assert state.status == SentinelStatus.ANALYZING_ISSUES
    print(f"  issues classified: {len(state.issue_analyses)}")
    print("  [PASS] issue_analyzer completed")

    # ---------------------------------------------------------------
    # Phase 4: Run issue_prioritizer
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PHASE 4: Run issue_prioritizer")
    print("=" * 60)

    result = await issue_prioritizer(state)
    state = state.model_copy(update=result)
    assert state.status == SentinelStatus.PRIORITIZING
    assert state.selected_issue is not None
    print(f"  selected: #{state.selected_issue.number} - {state.selected_issue.title}")

    # Show the search query that will be used
    query = f"{state.selected_issue.title} {state.selected_issue.body}"
    print(f"  search query: \"{query}\"")
    print("  [PASS] issue_prioritizer completed")

    # ---------------------------------------------------------------
    # Phase 5: Run retrieve_context
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PHASE 5: Run retrieve_context")
    print("=" * 60)

    result = await retrieve_context(state)

    print(f"  Returned keys:    {list(result.keys())}")
    print(f"  status:           {result.get('status')}")
    print(f"  current_agent:    {result.get('current_agent')}")
    print(f"  relevant_chunks:  {len(result.get('relevant_chunks', []))} items")

    assert result["status"] == SentinelStatus.RETRIEVING_CONTEXT
    assert result["current_agent"] == "retrieve_context"
    assert isinstance(result["relevant_chunks"], list)
    assert len(result["relevant_chunks"]) > 0, "Expected at least 1 chunk"
    print("  [PASS] retrieve_context returned correct status and chunks")

    # ---------------------------------------------------------------
    # Phase 6: Validate RetrievedChunk contents
    # ---------------------------------------------------------------
    chunks = result["relevant_chunks"]
    print("\n" + "=" * 60)
    print("PHASE 6: RetrievedChunk Contents")
    print("=" * 60)

    for i, chunk in enumerate(chunks):
        assert isinstance(chunk, RetrievedChunk), f"Item {i} is not RetrievedChunk"
        print(f"\n  --- Chunk {i+1} ---")
        print(f"  file_path:   {chunk.file_path}")
        print(f"  language:    {chunk.language}")
        print(f"  lines:       {chunk.start_line}-{chunk.end_line}")
        print(f"  score:       {chunk.score:.4f}")
        print(f"  content:     {chunk.content[:120]}{'...' if len(chunk.content) > 120 else ''}")

        assert chunk.file_path, "file_path should not be empty"
        assert chunk.content, "content should not be empty"
        assert chunk.score >= 0.0, f"score out of range: {chunk.score}"

    # Verify index.html is in the results (should be the top result)
    file_paths = [c.file_path for c in chunks]
    assert "index.html" in file_paths, f"Expected index.html in results, got: {file_paths}"
    print(f"\n  [PASS] All {len(chunks)} RetrievedChunk objects validated")
    print("  [PASS] index.html found in results")

    # ---------------------------------------------------------------
    # Phase 7: State transition verification
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("PHASE 7: State Transition Verification")
    print("=" * 60)

    updated_state = state.model_copy(update=result)

    print(f"  Before:  status={state.status}  chunks={len(state.relevant_chunks)}")
    print(f"  After:   status={updated_state.status}  chunks={len(updated_state.relevant_chunks)}")

    assert updated_state.status == SentinelStatus.RETRIEVING_CONTEXT
    assert len(updated_state.relevant_chunks) > 0
    # Previous state persists
    assert updated_state.repo_context is not None
    assert len(updated_state.issue_analyses) > 0
    assert updated_state.selected_issue is not None
    # Original state not mutated
    assert state.relevant_chunks == []

    print("  [PASS] State transition: PRIORITIZING -> RETRIEVING_CONTEXT")
    print("  [PASS] relevant_chunks stored in SentinelState")
    print("  [PASS] All prior state fields persist")
    print("  [PASS] Original state immutability preserved")

    # Simulate completion
    completed = updated_state.model_copy(
        update={"status": SentinelStatus.COMPLETED, "current_agent": ""}
    )
    assert completed.status == SentinelStatus.COMPLETED
    assert len(completed.relevant_chunks) > 0
    print("  [PASS] State transition: RETRIEVING_CONTEXT -> COMPLETED")

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
    print(f"  Repository:       {updated_state.repo_context.repository_name}")
    print(f"  Selected issue:   #{updated_state.selected_issue.number} - {updated_state.selected_issue.title}")
    print(f"  Chunks retrieved: {len(updated_state.relevant_chunks)}")
    for c in updated_state.relevant_chunks:
        print(f"    [{c.score:.4f}] {c.file_path} (L{c.start_line}-{c.end_line}) [{c.language}]")
    print()


if __name__ == "__main__":
    asyncio.run(main())
