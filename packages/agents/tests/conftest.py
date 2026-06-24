"""Shared pytest fixtures/config for the agents package.

Importing ``forge_workflows`` first fully initializes the workflows package
(state → graph → agents) in the correct order. The package graph has a latent
import cycle that only surfaces when ``forge_agents`` is imported *before*
``forge_workflows``; the application always imports workflows first, so priming
it here keeps the test import order consistent with production.
"""

from __future__ import annotations

import forge_workflows  # noqa: F401  (import for its initialization side effect)
