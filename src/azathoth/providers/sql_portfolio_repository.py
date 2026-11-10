"""The organizational model portfolio, in either database (ADR 0102)."""

from datetime import UTC, datetime

from azathoth.persistence import Database, IntegrityError, Row, Session, Table, require_text
from azathoth.providers.portfolio import (
    ModelPortfolioEntry,
)
from azathoth.providers.portfolio_provenance import PolicyDeclaration, PortfolioProvenance
from azathoth.revisions import Author, content_digest
from azathoth.sensitivity import DataPolicy

MODEL_PORTFOLIO_TABLES = (
    Table(
        name="model_portfolio_entries",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS
                model_portfolio_entries (
                    sequence {sequence},
                    identifier TEXT NOT NULL UNIQUE,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                model_portfolio_entries_provider_sequence
            ON model_portfolio_entries (
                provider,
                sequence
            )
            """,
        ),
    ),
)
"""The tables the model portfolio is kept in."""


def _fill_portfolio_provenance(
    session: Session,
    present: frozenset[str],
) -> None:
    """Record the provenance of every portfolio entry that lacks one, without author or time."""

    if "model_portfolio_entries" not in present:
        return

    rows = session.fetchall(
        """
        SELECT e.payload
        FROM model_portfolio_entries e
        WHERE NOT EXISTS (
            SELECT 1
            FROM model_portfolio_provenance p
            WHERE p.identifier = e.identifier
        )
        ORDER BY e.sequence
        """
    )

    for row in rows:
        entry = _entry(row[0])

        _insert_provenance(
            session,
            PortfolioProvenance(
                identifier=entry.identifier,
                content_digest=content_digest(entry),
            ),
        )


MODEL_PORTFOLIO_PROVENANCE_TABLES = (
    Table(
        name="model_portfolio_provenance",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS
                model_portfolio_provenance (
                    identifier TEXT NOT NULL PRIMARY KEY,
                    content_digest TEXT NOT NULL,
                    author_name TEXT,
                    author_email TEXT,
                    added_at TEXT
                )
            """,
        ),
        backfill=_fill_portfolio_provenance,
    ),
)
"""The table portfolio provenance is kept in (ADR 0122).

Its backfill records the provenance of entries added before it existed,
with their digest and no author or time.
"""


MODEL_PORTFOLIO_POLICY_TABLES = (
    Table(
        name="model_portfolio_policy_declarations",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS
                model_portfolio_policy_declarations (
                    identifier TEXT NOT NULL PRIMARY KEY,
                    author_name TEXT,
                    author_email TEXT,
                    declared_at TEXT NOT NULL
                )
            """,
        ),
    ),
)
"""The table recording who declared each portfolio entry's data policy, and when (ADR 0123).

Policies were first declared in this version, so there is nothing to
backfill.
"""


class SqlModelPortfolioRepository:
    """Persist authorized model portfolio entries in a database."""

    def __init__(
        self,
        database: Database,
    ) -> None:
        self._database = database
        database.prepare(
            (
                *MODEL_PORTFOLIO_TABLES,
                *MODEL_PORTFOLIO_PROVENANCE_TABLES,
                *MODEL_PORTFOLIO_POLICY_TABLES,
            )
        )

    def save(
        self,
        entry: ModelPortfolioEntry,
        *,
        author: Author | None = None,
    ) -> None:
        """Persist one entry without replacing existing policy, and record its provenance.

        An entry with a declared data policy records its author as having
        declared it, at the time it was added (ADR 0123).

        Raises:
            ValueError: An entry with the same identifier already exists.
        """

        added_at = datetime.now(UTC)

        try:
            with self._database.transaction() as session:
                session.execute(
                    """
                    INSERT INTO model_portfolio_entries (
                        identifier,
                        provider,
                        model,
                        payload
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        entry.identifier,
                        entry.provider,
                        entry.model,
                        entry.model_dump_json(),
                    ),
                )

                _insert_provenance(
                    session,
                    PortfolioProvenance(
                        identifier=entry.identifier,
                        content_digest=content_digest(entry),
                        author=author,
                        added_at=added_at,
                    ),
                )

                if not entry.data_policy.unknown:
                    _replace_declaration(
                        session,
                        PolicyDeclaration(
                            identifier=entry.identifier,
                            author=author,
                            declared_at=added_at,
                        ),
                    )
        except IntegrityError as exc:
            raise ValueError(f"Model portfolio entry {entry.identifier!r} already exists.") from exc

    def get(
        self,
        identifier: str,
    ) -> ModelPortfolioEntry | None:
        """Return one portfolio entry by identifier."""

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT payload
                FROM model_portfolio_entries
                WHERE identifier = ?
                """,
                (identifier,),
            )

        if row is None:
            return None

        return self._deserialize_payload(row[0])

    def delete(
        self,
        identifier: str,
    ) -> None:
        """Delete one authorized model entry and its provenance.

        Raises:
            ValueError: The entry does not exist.
        """

        with self._database.transaction() as session:
            deleted = session.execute(
                """
                DELETE FROM model_portfolio_entries
                WHERE identifier = ?
                """,
                (identifier,),
            )

            session.execute(
                """
                DELETE FROM model_portfolio_provenance
                WHERE identifier = ?
                """,
                (identifier,),
            )

            session.execute(
                """
                DELETE FROM model_portfolio_policy_declarations
                WHERE identifier = ?
                """,
                (identifier,),
            )

        if deleted == 0:
            raise ValueError(f"Model portfolio entry {identifier!r} does not exist.")

    def entries(
        self,
    ) -> tuple[ModelPortfolioEntry, ...]:
        """Return all portfolio entries in insertion order."""

        with self._database.transaction() as session:
            rows = session.fetchall(
                """
                SELECT payload
                FROM model_portfolio_entries
                ORDER BY sequence
                """
            )

        return tuple(self._deserialize_payload(row[0]) for row in rows)

    def set_data_policy(
        self,
        identifier: str,
        policy: DataPolicy,
        *,
        author: Author | None = None,
    ) -> ModelPortfolioEntry:
        """Declare what one entry's provider does with data, keeping its place and provenance.

        Who declared it, and when, replace any earlier declaration.

        Raises:
            ValueError: The entry does not exist.
        """

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT payload
                FROM model_portfolio_entries
                WHERE identifier = ?
                """,
                (identifier,),
            )

            if row is None:
                raise ValueError(f"Model portfolio entry {identifier!r} does not exist.")

            declared = _entry(row[0]).model_copy(update={"data_policy": policy})

            session.execute(
                """
                UPDATE model_portfolio_entries
                SET payload = ?
                WHERE identifier = ?
                """,
                (declared.model_dump_json(), identifier),
            )

            _replace_declaration(
                session,
                PolicyDeclaration(
                    identifier=identifier,
                    author=author,
                    declared_at=datetime.now(UTC),
                ),
            )

        return declared

    def policy_declaration(
        self,
        identifier: str,
    ) -> PolicyDeclaration | None:
        """Return who declared one entry's data policy and when, if it was declared."""

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT identifier, author_name, author_email, declared_at
                FROM model_portfolio_policy_declarations
                WHERE identifier = ?
                """,
                (identifier,),
            )

        return None if row is None else _declaration(row)

    def provenance(
        self,
        identifier: str,
    ) -> PortfolioProvenance | None:
        """Return the provenance of one portfolio entry, if it is in the portfolio."""

        with self._database.transaction() as session:
            row = session.fetchone(
                """
                SELECT identifier, content_digest, author_name, author_email, added_at
                FROM model_portfolio_provenance
                WHERE identifier = ?
                """,
                (identifier,),
            )

        return None if row is None else _provenance(row)

    @staticmethod
    def _deserialize_payload(
        payload: object,
    ) -> ModelPortfolioEntry:
        """Reconstruct one persisted portfolio entry."""

        return _entry(payload)


def _entry(
    payload: object,
) -> ModelPortfolioEntry:
    """Reconstruct one persisted portfolio entry."""

    return ModelPortfolioEntry.model_validate_json(
        require_text(payload, "Persisted model portfolio entry payload was not text.")
    )


def _insert_provenance(
    session: Session,
    provenance: PortfolioProvenance,
) -> None:
    """Insert one entry's provenance row."""

    author = provenance.author

    session.execute(
        """
        INSERT INTO model_portfolio_provenance (
            identifier,
            content_digest,
            author_name,
            author_email,
            added_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            provenance.identifier,
            provenance.content_digest,
            None if author is None else author.name,
            None if author is None else author.email,
            None if provenance.added_at is None else provenance.added_at.isoformat(),
        ),
    )


def _replace_declaration(
    session: Session,
    declaration: PolicyDeclaration,
) -> None:
    """Record one entry's policy declaration in place of any earlier one."""

    author = declaration.author

    session.execute(
        """
        DELETE FROM model_portfolio_policy_declarations
        WHERE identifier = ?
        """,
        (declaration.identifier,),
    )

    session.execute(
        """
        INSERT INTO model_portfolio_policy_declarations (
            identifier,
            author_name,
            author_email,
            declared_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            declaration.identifier,
            None if author is None else author.name,
            None if author is None else author.email,
            declaration.declared_at.isoformat(),
        ),
    )


def _declaration(
    row: Row,
) -> PolicyDeclaration:
    """Return the policy declaration one row holds."""

    name = row[1]
    email = row[2]

    return PolicyDeclaration(
        identifier=require_text(row[0], "A policy declaration identifier was not text."),
        author=(
            None
            if name is None
            else Author(
                name=require_text(name, "A policy declaration author name was not text."),
                email=(
                    None
                    if email is None
                    else require_text(email, "A policy declaration author email was not text.")
                ),
            )
        ),
        declared_at=datetime.fromisoformat(
            require_text(row[3], "A policy declaration time was not text.")
        ),
    )


def _provenance(
    row: Row,
) -> PortfolioProvenance:
    """Return the provenance one row holds."""

    name = row[2]
    email = row[3]
    added_at = row[4]

    return PortfolioProvenance(
        identifier=require_text(row[0], "A portfolio provenance identifier was not text."),
        content_digest=require_text(row[1], "A portfolio provenance digest was not text."),
        author=(
            None
            if name is None
            else Author(
                name=require_text(name, "A portfolio author name was not text."),
                email=(
                    None
                    if email is None
                    else require_text(email, "A portfolio author email was not text.")
                ),
            )
        ),
        added_at=(
            None
            if added_at is None
            else datetime.fromisoformat(
                require_text(added_at, "A portfolio provenance time was not text.")
            )
        ),
    )


__all__ = [
    "MODEL_PORTFOLIO_POLICY_TABLES",
    "MODEL_PORTFOLIO_PROVENANCE_TABLES",
    "MODEL_PORTFOLIO_TABLES",
    "SqlModelPortfolioRepository",
]
