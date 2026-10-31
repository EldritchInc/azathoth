"""Database initialization for the Azathoth CLI (ADR 0095)."""

import sqlite3
import sys

from azathoth.cli.configuration import CliRuntimeConfiguration
from azathoth.cli.tools import install_standard_tools


def initialize_database() -> int:
    """Create the configured database if needed and install the standard tools.

    The database is the one `AZATHOTH_DATABASE` names, or `azathoth.db` in the
    working directory. Missing parent directories are created. The database
    is shown as an absolute path, marked as created or existing, and the
    standard tool library is then installed exactly as by
    `azathoth tool install-standard`, so running `init` again is always safe.

    Initialization stops at the database and its tools. Authorizing models
    needs provider credentials, so it stays a separate step.
    """

    configuration = CliRuntimeConfiguration.from_environment()

    database = configuration.database.absolute()

    existed = database.exists()

    try:
        database.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        sqlite3.connect(database).close()
    except (OSError, sqlite3.Error) as exc:
        print(
            f"Unable to open database {database}: {exc}",
            file=sys.stderr,
        )

        return 1

    print(f"Database: {database} ({'existing' if existed else 'created'})")

    return install_standard_tools()


__all__ = [
    "initialize_database",
]
