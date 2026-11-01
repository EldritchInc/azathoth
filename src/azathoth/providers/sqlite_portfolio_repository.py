"""SQLite persistence for organizational model portfolio entries."""

from pathlib import Path

from azathoth.persistence import SQLiteDatabase
from azathoth.providers.sql_portfolio_repository import SqlModelPortfolioRepository


class SQLiteModelPortfolioRepository(SqlModelPortfolioRepository):
    """Persist authorized model portfolio entries in SQLite."""

    def __init__(
        self,
        database: str | Path,
    ) -> None:
        super().__init__(SQLiteDatabase(database))
