"""Sandbox runner for Sentinel Brain — real local test execution.

Executes the :class:`TestSpec`s authored by the ``TestDesignerAgent`` against the
patched files in a cloned workspace and reports real pass/fail :class:`TestResult`s.
Two execution paths:

- ``framework="html-validate"`` — runs the real ``html-validate`` CLI for HTML
  *validity* (well-formedness, accessibility, required attributes).
- ``framework="assertion"`` — evaluates structured content/DOM checks in-process:
  BeautifulSoup for ``dom_text``/``dom_attr``, regex/substring for ``content_*``.

Design (mirrors ``patch_executor.py`` / ``file_loader.py``):
    - Pure filesystem + subprocess utility — no LLM, no database, no HTTP, no ``app.*``.
    - Synchronous; the graph node wraps calls in ``asyncio.to_thread``.
    - A failing test is a *reported outcome* (:class:`TestResult` with ``passed=False``),
      never a raised exception. A missing runner binary or unparsable output is itself
      surfaced as a failing result.
    - **Never writes into the workspace.** The ``html-validate`` config is written to a
      temp file outside the tree; assertions read files in-memory. This keeps the git
      working tree clean so ``apply_patches`` rollback and ``GitService`` commit only ever
      see the intended code changes.
    - Instantiated once as a module-level singleton: ``sandbox_runner``.

The runner is kept behind the small :class:`SandboxRunner` Protocol so a future
Docker/managed-sandbox backend can be swapped in without touching the graph or agents.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol

from bs4 import BeautifulSoup

from forge_workflows.state import TestAssertion, TestResult, TestSpec

logger = logging.getLogger(__name__)

# Default html-validate ruleset. Overridable via HTML_VALIDATE_CONFIG (a path to a
# JSON config file). The runner writes this to a temp file when no override is given.
_DEFAULT_HTML_VALIDATE_CONFIG = '{"extends":["html-validate:recommended"]}'

# Hard ceiling on a single html-validate invocation (seconds).
_RUNNER_TIMEOUT_S = 120


def _resolve_html_validate_bin() -> str:
    """Locate the ``html-validate`` executable.

    Resolution order:
      1. ``HTML_VALIDATE_BIN`` env override (explicit wins).
      2. A ``html-validate`` on ``PATH``.
      3. The repo-local ``node_modules/.bin/html-validate`` — installed as a
         devDependency but normally absent from ``PATH``. The Sentinel repo root is
         ``parents[3]`` of this file (forge_agents/packages/agents/packages/root).

    Returns the env override or a resolved absolute path; falls back to the bare
    name ``"html-validate"`` so the caller still emits the actionable "not found"
    message if nothing is discoverable.
    """
    override = os.environ.get("HTML_VALIDATE_BIN")
    if override:
        return override

    on_path = shutil.which("html-validate")
    if on_path:
        return on_path

    repo_bin = Path(__file__).resolve().parents[3] / "node_modules" / ".bin" / "html-validate"
    if repo_bin.exists():
        return str(repo_bin)

    return "html-validate"


class SandboxRunner(Protocol):
    """Executes test specs against a workspace and returns real results.

    Implemented locally by :class:`LocalSandboxRunner`; a Docker/managed-sandbox
    backend can implement the same contract later.
    """

    def run(self, workspace_path: str, specs: list[TestSpec]) -> list[TestResult]:
        ...


class LocalSandboxRunner:
    """Runs test specs locally: ``html-validate`` subprocess + in-process assertions.

    Pure filesystem/subprocess utility — no LLM, no database, no HTTP.
    """

    def run(self, workspace_path: str, specs: list[TestSpec]) -> list[TestResult]:
        """Execute every spec and return one :class:`TestResult` per spec.

        Args:
            workspace_path: Absolute path to the cloned repository root.
            specs: The test cases authored by the TestDesignerAgent.

        Returns:
            One result per spec, in order. Never raises on a failing or broken test.
        """
        if not specs:
            logger.info("No test specs to execute")
            return []

        results: list[TestResult] = []
        for spec in specs:
            if spec.framework == "html-validate":
                results.append(self._run_html_validate(workspace_path, spec))
            else:
                results.append(self._run_assertions(workspace_path, spec))

        logger.info(
            "Executed %d test spec(s): %d passed",
            len(results),
            sum(r.passed for r in results),
        )
        return results

    # ------------------------------------------------------------------
    # html-validate
    # ------------------------------------------------------------------

    def _run_html_validate(self, workspace_path: str, spec: TestSpec) -> TestResult:
        """Run the real ``html-validate`` CLI against ``spec.target_file``."""
        target = self._safe_target(workspace_path, spec.target_file)
        if target is None or not target.exists():
            return TestResult(
                name=spec.name,
                passed=False,
                output="",
                error=f"Target file not found in workspace: {spec.target_file}",
                spec_id=spec.id,
            )

        binary = _resolve_html_validate_bin()
        config_path = os.environ.get("HTML_VALIDATE_CONFIG")
        tmp_config: str | None = None
        if not config_path:
            fd, tmp_config = tempfile.mkstemp(prefix="forge-htmlvalidate-", suffix=".json")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(_DEFAULT_HTML_VALIDATE_CONFIG)
            config_path = tmp_config

        try:
            proc = subprocess.run(
                [binary, "--formatter", "json", "--config", config_path, str(target)],
                capture_output=True,
                text=True,
                cwd=workspace_path,
                timeout=_RUNNER_TIMEOUT_S,
            )
        except FileNotFoundError:
            return TestResult(
                name=spec.name,
                passed=False,
                output="",
                error=(
                    f"html-validate runner not found ('{binary}'). Install it "
                    "(npm i -D html-validate) or set HTML_VALIDATE_BIN."
                ),
                spec_id=spec.id,
            )
        except subprocess.TimeoutExpired:
            return TestResult(
                name=spec.name,
                passed=False,
                output="",
                error=f"html-validate timed out after {_RUNNER_TIMEOUT_S}s",
                spec_id=spec.id,
                exit_code=None,
            )
        finally:
            if tmp_config:
                Path(tmp_config).unlink(missing_ok=True)

        return self._parse_html_validate(spec, proc)

    @staticmethod
    def _parse_html_validate(
        spec: TestSpec, proc: subprocess.CompletedProcess[str]
    ) -> TestResult:
        """Turn an html-validate process result into a TestResult.

        Pass is defined as zero *errors* (warnings do not fail the test). Exit code 0
        with no output also passes (html-validate emits ``[]`` or nothing for clean files).
        """
        stdout = (proc.stdout or "").strip()
        if not stdout:
            # No findings printed; trust the exit code (0 = clean).
            passed = proc.returncode == 0
            return TestResult(
                name=spec.name,
                passed=passed,
                output="html-validate: no issues reported." if passed else (proc.stderr or "").strip(),
                error=None if passed else "html-validate reported a non-zero exit with no JSON output.",
                spec_id=spec.id,
                exit_code=proc.returncode,
            )

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return TestResult(
                name=spec.name,
                passed=False,
                output=stdout[:2000],
                error="Could not parse html-validate JSON output.",
                spec_id=spec.id,
                exit_code=proc.returncode,
            )

        error_count = 0
        lines: list[str] = []
        for file_result in payload if isinstance(payload, list) else []:
            error_count += int(file_result.get("errorCount", 0))
            for msg in file_result.get("messages", []):
                sev = "error" if msg.get("severity") == 2 else "warning"
                lines.append(
                    f"  [{sev}] line {msg.get('line')}:{msg.get('column')} "
                    f"{msg.get('ruleId')} — {msg.get('message')}"
                )

        passed = error_count == 0
        summary = (
            f"html-validate: {error_count} error(s) in {spec.target_file}."
            if not passed
            else f"html-validate: {spec.target_file} is valid."
        )
        output = summary + ("\n" + "\n".join(lines) if lines else "")
        return TestResult(
            name=spec.name,
            passed=passed,
            output=output,
            error=None if passed else f"{error_count} validation error(s).",
            spec_id=spec.id,
            exit_code=proc.returncode,
        )

    # ------------------------------------------------------------------
    # In-process content / DOM assertions
    # ------------------------------------------------------------------

    def _run_assertions(self, workspace_path: str, spec: TestSpec) -> TestResult:
        """Evaluate every assertion in ``spec`` against ``spec.target_file``."""
        target = self._safe_target(workspace_path, spec.target_file)
        if target is None or not target.exists():
            return TestResult(
                name=spec.name,
                passed=False,
                output="",
                error=f"Target file not found in workspace: {spec.target_file}",
                spec_id=spec.id,
            )

        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return TestResult(
                name=spec.name,
                passed=False,
                output="",
                error=f"Could not read {spec.target_file}: {exc}",
                spec_id=spec.id,
            )

        if not spec.assertions:
            return TestResult(
                name=spec.name,
                passed=False,
                output="",
                error="Assertion spec has no assertions to evaluate.",
                spec_id=spec.id,
            )

        soup: BeautifulSoup | None = None
        lines: list[str] = []
        all_passed = True
        for assertion in spec.assertions:
            if assertion.type in ("dom_text", "dom_attr") and soup is None:
                soup = BeautifulSoup(content, "html.parser")
            ok, detail = self._evaluate(assertion, content, soup)
            all_passed = all_passed and ok
            lines.append(f"  [{'PASS' if ok else 'FAIL'}] {detail}")

        return TestResult(
            name=spec.name,
            passed=all_passed,
            output="\n".join(lines),
            error=None if all_passed else "One or more assertions failed.",
            spec_id=spec.id,
        )

    @staticmethod
    def _evaluate(
        assertion: TestAssertion, content: str, soup: BeautifulSoup | None
    ) -> tuple[bool, str]:
        """Evaluate a single assertion; returns ``(passed, human_readable_detail)``."""
        t = assertion.type

        if t == "content_contains":
            needle = assertion.contains or ""
            return (needle in content), f"content contains {needle!r}"

        if t == "content_regex":
            pattern = assertion.pattern or ""
            try:
                ok = re.search(pattern, content) is not None
            except re.error as exc:
                return False, f"invalid regex {pattern!r}: {exc}"
            return ok, f"content matches /{pattern}/"

        # dom_text / dom_attr
        assert soup is not None  # set by caller for DOM assertion types
        selector = assertion.selector or ""
        try:
            element = soup.select_one(selector)
        except Exception as exc:  # invalid selector syntax
            return False, f"invalid selector {selector!r}: {exc}"
        if element is None:
            return False, f"selector {selector!r} matched no element"

        if t == "dom_text":
            actual = element.get_text(strip=True)
            label = f"text of {selector!r}"
        else:  # dom_attr
            actual = element.get(assertion.attr or "")
            actual = actual if isinstance(actual, str) else (" ".join(actual) if actual else None)
            label = f"attribute {assertion.attr!r} of {selector!r}"

        if assertion.expected is not None:
            return (actual == assertion.expected), (
                f"{label} == {assertion.expected!r} (actual: {actual!r})"
            )
        if assertion.contains is not None:
            return (actual is not None and assertion.contains in actual), (
                f"{label} contains {assertion.contains!r} (actual: {actual!r})"
            )
        return False, f"{label}: no 'expected' or 'contains' specified"

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_target(workspace_path: str, file_path: str) -> Path | None:
        """Resolve ``file_path`` within the workspace; reject path traversal.

        Mirrors ``PatchExecutor._safe_target``.
        """
        root = Path(workspace_path).resolve()
        candidate = (root / file_path).resolve()
        if candidate == root or root not in candidate.parents:
            return None
        return candidate


sandbox_runner: SandboxRunner = LocalSandboxRunner()
