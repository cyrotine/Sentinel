"""Tests for TestDesignerAgent parsing and deterministic fallback."""

from __future__ import annotations

from forge_agents.test_designer import TestDesignerAgent
from forge_workflows.state import FullFileContext, Plan


def test_build_specs_parses_assertion_and_html_validate() -> None:
    parsed = {
        "tests": [
            {
                "id": "test_1",
                "name": "h1 label",
                "acceptance_criterion": "label reads Welcome",
                "target_file": "index.html",
                "framework": "assertion",
                "assertions": [
                    {"type": "dom_text", "selector": "h1", "expected": "Welcome"}
                ],
            },
            {
                "id": "test_2",
                "name": "valid html",
                "target_file": "index.html",
                "framework": "html-validate",
            },
        ]
    }
    specs = TestDesignerAgent._build_specs(parsed)
    assert [s.framework for s in specs] == ["assertion", "html-validate"]
    assert specs[0].assertions[0].type == "dom_text"


def test_build_specs_drops_unusable_entries() -> None:
    parsed = {
        "tests": [
            {"name": "no target", "framework": "assertion", "assertions": []},
            {"name": "empty path", "target_file": "", "framework": "html-validate"},
            {
                "name": "assertion with no valid assertions",
                "target_file": "x.html",
                "framework": "assertion",
                "assertions": [{"type": "not_a_real_type"}],
            },
        ]
    }
    assert TestDesignerAgent._build_specs(parsed) == []


def test_fallback_emits_one_html_validate_spec_per_changed_html() -> None:
    plan = Plan(affected_files=["index.html", "about.html", "style.css"])
    specs = TestDesignerAgent._fallback_specs(plan, [])
    assert [s.target_file for s in specs] == ["index.html", "about.html"]
    assert all(s.framework == "html-validate" for s in specs)


def test_fallback_uses_loaded_files_when_plan_has_no_html() -> None:
    plan = Plan(affected_files=["style.css"])
    files = [FullFileContext(file_path="page.html", content="<html></html>", line_count=1)]
    specs = TestDesignerAgent._fallback_specs(plan, files)
    assert [s.target_file for s in specs] == ["page.html"]
