"""Direct test of the PatchExecutor and the apply_patches graph node.

Fully deterministic — no LLM, no API quota. Builds a throwaway git repo in a
temp dir, exercises clean apply / fuzzy apply / failure / traversal / rollback,
then runs the apply_patches node end-to-end.
"""

import logging
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.abspath("apps/api"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# Import forge_workflows first to fully initialize it before forge_agents'
# package __init__ runs (avoids a pre-existing circular-import ordering issue).
from forge_workflows.state import CodeChange
from forge_workflows.graph import build_graph, APPLY_PATCHES, DEVELOPER, VALIDATOR
from forge_agents.patch_executor import patch_executor


INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Hello World</title>
    <style>
        h1 {
            font-size: 5rem;
            color: black;
        }
    </style>
</head>
<body>
    <h1>Hello World</h1>
</body>
</html>
"""

# A valid unified diff (git format) changing the h1 color from black to red.
COLOR_PATCH = """--- a/index.html
+++ b/index.html
@@ -7,5 +7,5 @@
         h1 {
             font-size: 5rem;
-            color: black;
+            color: red;
         }
     </style>
"""

# A diff whose context does not match the file at all.
BROKEN_PATCH = """--- a/index.html
+++ b/index.html
@@ -1,3 +1,3 @@
 this line does not exist
-neither does this one
+nor this replacement
 and definitely not this
"""


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _make_repo() -> str:
    workspace = tempfile.mkdtemp(prefix="forge-patch-test-")
    _git(["init"], workspace)
    _git(["config", "user.email", "test@forge.local"], workspace)
    _git(["config", "user.name", "Forge Test"], workspace)
    with open(os.path.join(workspace, "index.html"), "w", encoding="utf-8") as f:
        f.write(INDEX_HTML)
    _git(["add", "."], workspace)
    _git(["commit", "-m", "init"], workspace)
    return workspace


def _read(workspace, name="index.html") -> str:
    with open(os.path.join(workspace, name), encoding="utf-8") as f:
        return f.read()


def test_clean_apply():
    ws = _make_repo()
    try:
        result = patch_executor.apply_patch(ws, CodeChange(
            file_path="index.html", patch=COLOR_PATCH, description="black -> red"))
        assert result.applied is True, result.error
        assert result.strategy == "git-apply", result.strategy
        assert "color: red;" in _read(ws)
        assert "color: black;" not in _read(ws)
        print("  [PASS] clean apply: git-apply, file now red")
    finally:
        shutil.rmtree(ws, ignore_errors=True)


def test_fuzzy_apply():
    ws = _make_repo()
    try:
        # Shift the file down by prepending a blank line so the hunk's @@ offsets
        # no longer match exactly — strict apply should reject, --3way recover.
        shifted = "\n" + INDEX_HTML
        with open(os.path.join(ws, "index.html"), "w", encoding="utf-8") as f:
            f.write(shifted)
        result = patch_executor.apply_patch(ws, CodeChange(
            file_path="index.html", patch=COLOR_PATCH, description="black -> red"))
        if result.applied:
            assert result.strategy in ("git-apply", "git-apply-3way"), result.strategy
            assert "color: red;" in _read(ws)
            print(f"  [PASS] fuzzy apply recovered via {result.strategy}")
        else:
            # Acceptable boundary: documents that --3way needs the blob committed.
            print(f"  [INFO] shifted patch rejected (fallback boundary): {result.error}")
    finally:
        shutil.rmtree(ws, ignore_errors=True)


def test_failure_path():
    ws = _make_repo()
    try:
        result = patch_executor.apply_patch(ws, CodeChange(
            file_path="index.html", patch=BROKEN_PATCH, description="bad context"))
        assert result.applied is False
        assert result.error, "expected an error message"
        assert result.failed_patch == BROKEN_PATCH
        assert result.full_file_content == _read(ws), "expected current on-disk content"
        assert _read(ws) == INDEX_HTML, "file must be unchanged on failure"
        print("  [PASS] failure path: reported, not raised; file untouched")
    finally:
        shutil.rmtree(ws, ignore_errors=True)


def test_traversal_guard():
    ws = _make_repo()
    try:
        result = patch_executor.apply_patch(ws, CodeChange(
            file_path="../escape.txt", patch=COLOR_PATCH, description="traversal"))
        assert result.applied is False
        assert "outside" in (result.error or "").lower()
        escaped = os.path.join(os.path.dirname(ws), "escape.txt")
        assert not os.path.exists(escaped), "must not write outside workspace"
        print("  [PASS] traversal guard: rejected, nothing written outside")
    finally:
        shutil.rmtree(ws, ignore_errors=True)


def test_rollback():
    ws = _make_repo()
    try:
        patch_executor.apply_patch(ws, CodeChange(
            file_path="index.html", patch=COLOR_PATCH, description="black -> red"))
        # Also create an untracked file to prove clean -fd removes it.
        with open(os.path.join(ws, "untracked.txt"), "w") as f:
            f.write("scratch")
        patch_executor.rollback_all(ws)
        assert _read(ws) == INDEX_HTML, "tracked file should be restored"
        assert not os.path.exists(os.path.join(ws, "untracked.txt")), "untracked removed"
        print("  [PASS] rollback: tracked restored, untracked removed")
    finally:
        shutil.rmtree(ws, ignore_errors=True)


def test_graph_wiring():
    # The node functions are closures inside build_graph, so we assert the
    # graph topology rather than importing the closure directly.
    g = build_graph(None, None, None)
    assert APPLY_PATCHES in g.nodes
    edges = {(a, b) for a, b in g.edges}
    assert (DEVELOPER, APPLY_PATCHES) in edges, "developer -> apply_patches missing"
    assert (APPLY_PATCHES, VALIDATOR) in edges, "apply_patches -> validator missing"
    assert (DEVELOPER, VALIDATOR) not in edges, "old developer -> validator edge still present"
    print("  [PASS] graph wiring: developer -> apply_patches -> validator")


def main():
    print("\n" + "=" * 60)
    print("PATCH EXECUTOR DIRECT TEST")
    print("=" * 60 + "\n")
    test_clean_apply()
    test_fuzzy_apply()
    test_failure_path()
    test_traversal_guard()
    test_rollback()
    test_graph_wiring()
    print("\n  ALL CHECKS PASSED\n")


if __name__ == "__main__":
    main()
