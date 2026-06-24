"""Tests for the LocalSandboxRunner — proves test execution is *real*, not simulated."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from forge_agents.sandbox_runner import LocalSandboxRunner
from forge_workflows.state import TestAssertion, TestSpec

# Repo-root html-validate binary installed for local execution.
_HTML_VALIDATE_BIN = Path(__file__).parents[3] / "node_modules" / ".bin" / "html-validate"

VALID_HTML = (
    "<!DOCTYPE html>\n"
    '<html lang="en">\n'
    '<head><meta charset="utf-8"><title>x</title></head>\n'
    '<body><h1>Welcome</h1><a class="cta" href="/signup">Join</a></body>\n'
    "</html>\n"
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text(VALID_HTML, encoding="utf-8")
    (tmp_path / "style.css").write_text("h1 { color: #1a1a1a; }\n", encoding="utf-8")
    return tmp_path


def test_dom_text_assertion_passes_on_correct_content(workspace: Path) -> None:
    spec = TestSpec(
        id="t1",
        name="h1 label",
        target_file="index.html",
        framework="assertion",
        assertions=[TestAssertion(type="dom_text", selector="h1", expected="Welcome")],
    )
    [result] = LocalSandboxRunner().run(str(workspace), [spec])
    assert result.passed is True
    assert result.spec_id == "t1"


def test_dom_text_assertion_fails_on_wrong_content(workspace: Path) -> None:
    spec = TestSpec(
        id="t2",
        name="wrong label",
        target_file="index.html",
        framework="assertion",
        assertions=[TestAssertion(type="dom_text", selector="h1", expected="Goodbye")],
    )
    [result] = LocalSandboxRunner().run(str(workspace), [spec])
    assert result.passed is False
    assert result.error


def test_dom_attr_and_regex_assertions(workspace: Path) -> None:
    specs = [
        TestSpec(
            id="t3",
            name="cta href",
            target_file="index.html",
            framework="assertion",
            assertions=[
                TestAssertion(type="dom_attr", selector="a.cta", attr="href", expected="/signup")
            ],
        ),
        TestSpec(
            id="t4",
            name="css color",
            target_file="style.css",
            framework="assertion",
            assertions=[TestAssertion(type="content_regex", pattern=r"color:\s*#1a1a1a")],
        ),
    ]
    results = LocalSandboxRunner().run(str(workspace), specs)
    assert all(r.passed for r in results)


def test_missing_target_file_is_reported_not_raised(workspace: Path) -> None:
    spec = TestSpec(
        id="t5",
        name="missing",
        target_file="nope.html",
        framework="assertion",
        assertions=[TestAssertion(type="content_contains", contains="x")],
    )
    [result] = LocalSandboxRunner().run(str(workspace), [spec])
    assert result.passed is False
    assert "not found" in (result.error or "").lower()


def test_path_traversal_is_rejected(workspace: Path) -> None:
    spec = TestSpec(
        id="t6",
        name="escape",
        target_file="../../etc/hosts",
        framework="assertion",
        assertions=[TestAssertion(type="content_contains", contains="root")],
    )
    [result] = LocalSandboxRunner().run(str(workspace), [spec])
    assert result.passed is False


@pytest.mark.skipif(
    not _HTML_VALIDATE_BIN.exists(),
    reason="html-validate binary not installed (run: pnpm add -w -D html-validate)",
)
def test_html_validate_runs_for_real(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTML_VALIDATE_BIN", str(_HTML_VALIDATE_BIN))

    valid_spec = TestSpec(
        id="hv1", name="valid html", target_file="index.html", framework="html-validate"
    )
    [ok] = LocalSandboxRunner().run(str(workspace), [valid_spec])
    assert ok.passed is True
    assert ok.exit_code == 0

    # An <img> without alt is a real html-validate error → real failing result.
    (workspace / "bad.html").write_text(
        '<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8"><title>x</title></head>'
        "<body><img src=\"a.png\"></body></html>\n",
        encoding="utf-8",
    )
    bad_spec = TestSpec(
        id="hv2", name="invalid html", target_file="bad.html", framework="html-validate"
    )
    [bad] = LocalSandboxRunner().run(str(workspace), [bad_spec])
    assert bad.passed is False
    assert bad.exit_code != 0


def test_missing_runner_binary_is_reported(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTML_VALIDATE_BIN", "definitely-not-a-real-binary-xyz")
    spec = TestSpec(
        id="hv3", name="valid html", target_file="index.html", framework="html-validate"
    )
    [result] = LocalSandboxRunner().run(str(workspace), [spec])
    assert result.passed is False
    assert "not found" in (result.error or "").lower()
