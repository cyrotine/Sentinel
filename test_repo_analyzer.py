"""Test script to run the repo_analyzer node against TempRepo."""

import asyncio
import logging
import sys
from pprint import pprint

# Ensure apps/api is in the path to allow imports of DB layer
import os
sys.path.insert(0, os.path.abspath("apps/api"))

from app.database import AsyncSessionLocal
from app.repositories import repository_repo
from forge_workflows.state import SentinelState
from forge_workflows.graph import repo_analyzer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Connecting to DB to find TempRepo...")
    async with AsyncSessionLocal() as session:
        repos = await repository_repo.list_all(session)
        temp_repo = next((r for r in repos if "TempRepo" in r.name), None)
        
        if not temp_repo:
            logger.error("TempRepo not found in the database. Ensure it has been ingested.")
            return
            
        logger.info("Found TempRepo: %s (ID: %s)", temp_repo.full_name, temp_repo.id)
        repo_id = str(temp_repo.id)

    # Prepare initial state
    state = SentinelState(repository_id=repo_id)
    
    logger.info("Running repo_analyzer node...")
    try:
        result = await repo_analyzer(state)
        
        logger.info("\n=== Analysis Complete ===")
        logger.info("Status: %s", result.get("status"))
        logger.info("Current Agent: %s", result.get("current_agent"))
        
        repo_context = result.get("repo_context")
        if repo_context:
            print("\nRepoContext Output:")
            pprint(repo_context.model_dump())
        else:
            logger.error("No repo_context returned!")
            
    except Exception as e:
        logger.exception("Failed to run repo_analyzer: %s", e)

if __name__ == "__main__":
    asyncio.run(main())
