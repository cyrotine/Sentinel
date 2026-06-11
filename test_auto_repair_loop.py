"""Unit tests for Phase 7 — Auto Repair Loop.

Pure-logic tests (no DB, no LLM, no network), runnable directly:

    .venv/bin/python test_auto_repair_loop.py

Covers:
  1. route_after_apply_patches — failed+budget / applied / budget-exhausted
  2. _build_repair_context — None on first pass; populated per trigger
  3. DeveloperAgent._build_repair_block — echoes the failed diff + file content
  4. DeveloperAgent._build_prompt — identical output when repair_context is None
"""

from __future__ import annotations

# Import forge_workflows first: the package graph imports forge_agents, so entering
# via forge_agents would hit a partially-initialized module (matches app import order).
from forge_workflows.graph import _build_repair_context, route_after_apply_patches
from forge_workflows.state import (
    PatchResult,
    Plan,
    RepoContext,
    Review,
    SelectedIssue,
    SentinelState,
    ValidationResult,
)
from forge_agents.developer import DeveloperAgent


def _failed_patch() -> PatchResult:
    return PatchResult(
        file_path="index.html",
        applied=False,
        error="error: patch failed: index.html:12",
        failed_patch="--- a/index.html\n+++ b/index.html\n@@ bad hunk @@",
        full_file_content="<h1>Original</h1>",
    )


def test_route_after_apply_patches() -> None:
    s = SentinelState(repository_id="r", iteration=0, max_iterations=3)

    # Failed patch + budget remaining -> repair.
    s.patch_results = [_failed_patch()]
    assert route_after_apply_patches(s) == "developer"

    # Budget exhausted -> proceed despite failure.
    s.iteration = 3
    assert route_after_apply_patches(s) == "validator"

    # All applied -> proceed.
    s.iteration = 0
    s.patch_results = [PatchResult(file_path="index.html", applied=True, strategy="git-apply")]
    assert route_after_apply_patches(s) == "validator"

    # No patch results at all -> proceed.
    s.patch_results = []
    assert route_after_apply_patches(s) == "validator"
    print("[PASS] route_after_apply_patches")


def test_build_repair_context() -> None:
    # First pass, no failure signal -> None.
    s = SentinelState(repository_id="r", iteration=0)
    assert _build_repair_context(s) is None

    # Passing validation + approved review -> still None.
    s.validation_result = ValidationResult(passed=True)
    s.review = Review(approved=True)
    assert _build_repair_context(s) is None

    # Each trigger populates its lists.
    s2 = SentinelState(repository_id="r", iteration=1)
    s2.patch_results = [_failed_patch()]
    s2.validation_result = ValidationResult(passed=False, issues=["i1"], suggestions=["s1"])
    s2.review = Review(
        approved=False, comments=["c1"], security_issues=["sec1"], suggestions=["rs1"]
    )
    rc = _build_repair_context(s2)
    assert rc is not None
    assert set(rc.triggers) == {"patch_failed", "validation_failed", "review_rejected"}
    assert rc.iteration == 1
    assert len(rc.failed_patches) == 1
    assert rc.validation_issues == ["i1"] and rc.validation_suggestions == ["s1"]
    assert rc.review_comments == ["c1"]
    assert rc.review_security_issues == ["sec1"]
    assert rc.review_suggestions == ["rs1"]

    # Only a rejecting review -> single trigger, no validation noise.
    s3 = SentinelState(repository_id="r", iteration=2)
    s3.review = Review(approved=False, suggestions=["fix it"])
    rc3 = _build_repair_context(s3)
    assert rc3 is not None and rc3.triggers == ["review_rejected"]
    assert rc3.validation_issues == [] and rc3.failed_patches == []
    print("[PASS] _build_repair_context")


def test_build_repair_block() -> None:
    s = SentinelState(repository_id="r", iteration=1)
    s.patch_results = [_failed_patch()]
    s.validation_result = ValidationResult(passed=False, issues=["missing alt"], suggestions=[])
    s.review = Review(approved=False, security_issues=["xss risk"])
    rc = _build_repair_context(s)
    assert rc is not None

    block = DeveloperAgent._build_repair_block(rc)
    assert "PREVIOUS ATTEMPT FAILED" in block
    assert "index.html" in block
    assert "@@ bad hunk @@" in block          # the rejected diff
    assert "<h1>Original</h1>" in block        # the current on-disk content
    assert "missing alt" in block              # validation issue
    assert "xss risk" in block                 # review security issue
    assert "Do not repeat the rejected diff" in block
    print("[PASS] _build_repair_block")


def test_first_attempt_prompt_unchanged() -> None:
    plan = Plan(affected_files=["index.html"], approach_reasoning="change the title")
    issue = SelectedIssue(issue_id="i", number=1, title="Fix title")
    repo = RepoContext(repository_name="owner/repo")
    dev = DeveloperAgent(llm=None)  # type: ignore[arg-type]

    no_arg = dev._build_prompt(plan, issue, repo, [], [])
    explicit_none = dev._build_prompt(plan, issue, repo, [], [], None)
    assert no_arg == explicit_none
    assert "PREVIOUS ATTEMPT FAILED" not in no_arg
    print("[PASS] first-attempt prompt unchanged")


def main() -> None:
    test_route_after_apply_patches()
    test_build_repair_context()
    test_build_repair_block()
    test_first_attempt_prompt_unchanged()
    print("\nALL TESTS PASSED")


if __name__ == "__main__":
    main()
