from app.models.base import Base

# Import all models so Base.metadata is populated for Alembic
from app.models.ingestion_run import IngestionRun  # noqa: F401
from app.models.issue import Issue  # noqa: F401
from app.models.repository import Repository  # noqa: F401
from app.models.repository_file import RepositoryFile  # noqa: F401

__all__ = ["Base", "IngestionRun", "Issue", "Repository", "RepositoryFile"]
