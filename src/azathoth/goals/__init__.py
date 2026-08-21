"""Goal domain models."""

from azathoth.goals.catalog import GoalCatalog
from azathoth.goals.catalog_loader import GoalCatalogLoader
from azathoth.goals.memory_repository import (
    InMemoryGoalRepository,
    require_goal_repository,
)
from azathoth.goals.models import Goal
from azathoth.goals.repository import GoalRepository
from azathoth.goals.sqlite_repository import SQLiteGoalRepository

__all__ = [
    "Goal",
    "GoalCatalog",
    "GoalCatalogLoader",
    "GoalRepository",
    "InMemoryGoalRepository",
    "SQLiteGoalRepository",
    "require_goal_repository",
]
