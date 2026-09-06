"""SQLite connection management, schema migrations, and safe database copies."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .errors import ConflictError, DatabaseNotInitializedError, ValidationError


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str


MIGRATIONS = (
    Migration(
        1,
        "initial_ledger",
        r"""
        CREATE TABLE accounts (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            kind TEXT NOT NULL CHECK (kind IN (
                'asset', 'liability', 'income', 'expense', 'equity', 'receivable'
            )),
            role TEXT NOT NULL CHECK (role IN ('user', 'category', 'party', 'system')),
            currency TEXT NOT NULL CHECK (
                length(currency) = 3 AND currency = upper(currency)
            ),
            archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1)),
            created_at TEXT NOT NULL
        );

        CREATE TABLE raw_messages (
            id TEXT PRIMARY KEY,
            channel TEXT NOT NULL,
            external_id TEXT,
            received_at TEXT NOT NULL,
            content TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK (
                status IN ('pending', 'proposed', 'confirmed', 'rejected', 'failed')
            ),
            parser_version TEXT,
            model_id TEXT,
            confidence TEXT,
            UNIQUE (channel, external_id)
        );

        CREATE TABLE transactions (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL CHECK (kind IN (
                'opening', 'expense', 'income', 'transfer', 'refund',
                'reimbursement', 'reversal', 'adjustment'
            )),
            amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
            currency TEXT NOT NULL CHECK (
                length(currency) = 3 AND currency = upper(currency)
            ),
            occurred_on TEXT NOT NULL CHECK (
                length(occurred_on) = 10 AND substr(occurred_on, 5, 1) = '-'
                AND substr(occurred_on, 8, 1) = '-'
            ),
            description TEXT NOT NULL,
            payee TEXT,
            status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'posted')),
            raw_input TEXT,
            raw_message_id TEXT REFERENCES raw_messages(id),
            actor TEXT NOT NULL,
            source TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            reversed_by_id TEXT UNIQUE REFERENCES transactions(id)
        );

        CREATE TABLE postings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id TEXT NOT NULL REFERENCES transactions(id) ON DELETE RESTRICT,
            account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
            amount_minor INTEGER NOT NULL CHECK (amount_minor != 0),
            memo TEXT
        );

        CREATE TABLE transaction_links (
            from_transaction_id TEXT NOT NULL REFERENCES transactions(id) ON DELETE RESTRICT,
            to_transaction_id TEXT NOT NULL REFERENCES transactions(id) ON DELETE RESTRICT,
            relation TEXT NOT NULL CHECK (relation IN (
                'refund_of', 'reimbursement_of', 'reversal_of', 'correction_of'
            )),
            PRIMARY KEY (from_transaction_id, to_transaction_id, relation),
            CHECK (from_transaction_id != to_transaction_id)
        );

        CREATE TABLE audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            actor TEXT NOT NULL,
            source TEXT NOT NULL,
            reason TEXT,
            before_json TEXT,
            after_json TEXT,
            created_at TEXT NOT NULL
        );

        CREATE INDEX idx_postings_transaction ON postings(transaction_id);
        CREATE INDEX idx_postings_account ON postings(account_id);
        CREATE INDEX idx_transactions_occurred ON transactions(occurred_on, created_at);
        CREATE INDEX idx_transactions_kind ON transactions(kind, occurred_on);
        CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id, created_at);

        CREATE VIEW posted_postings AS
        SELECT p.id, p.transaction_id, p.account_id, p.amount_minor, p.memo
        FROM postings p
        JOIN transactions t ON t.id = p.transaction_id
        WHERE t.status = 'posted';

        CREATE TRIGGER validate_transaction_before_post
        BEFORE UPDATE OF status ON transactions
        WHEN OLD.status = 'draft' AND NEW.status = 'posted'
        BEGIN
            SELECT CASE WHEN (
                SELECT count(*) FROM postings WHERE transaction_id = NEW.id
            ) < 2 THEN RAISE(ABORT, 'posted transaction requires at least two postings') END;
            SELECT CASE WHEN coalesce((
                SELECT sum(amount_minor) FROM postings WHERE transaction_id = NEW.id
            ), 1) != 0 THEN RAISE(ABORT, 'posted transaction must balance') END;
            SELECT CASE WHEN EXISTS (
                SELECT 1 FROM postings p JOIN accounts a ON a.id = p.account_id
                WHERE p.transaction_id = NEW.id AND a.currency != NEW.currency
            ) THEN RAISE(ABORT, 'posting currency does not match transaction') END;
        END;

        CREATE TRIGGER no_posting_insert_for_posted_transaction
        BEFORE INSERT ON postings
        WHEN (SELECT status FROM transactions WHERE id = NEW.transaction_id) = 'posted'
        BEGIN
            SELECT RAISE(ABORT, 'postings of a posted transaction are immutable');
        END;

        CREATE TRIGGER no_posting_update_for_posted_transaction
        BEFORE UPDATE ON postings
        WHEN (SELECT status FROM transactions WHERE id = OLD.transaction_id) = 'posted'
        BEGIN
            SELECT RAISE(ABORT, 'postings of a posted transaction are immutable');
        END;

        CREATE TRIGGER no_posting_delete_for_posted_transaction
        BEFORE DELETE ON postings
        WHEN (SELECT status FROM transactions WHERE id = OLD.transaction_id) = 'posted'
        BEGIN
            SELECT RAISE(ABORT, 'postings of a posted transaction are immutable');
        END;

        CREATE TRIGGER no_posted_transaction_financial_update
        BEFORE UPDATE OF kind, amount_minor, currency, occurred_on, description, payee,
            status, raw_input, raw_message_id, actor, source, metadata_json, created_at
        ON transactions
        WHEN OLD.status = 'posted'
        BEGIN
            SELECT RAISE(ABORT, 'posted transaction is immutable; create a reversal');
        END;

        CREATE TRIGGER no_posted_transaction_delete
        BEFORE DELETE ON transactions
        WHEN OLD.status = 'posted'
        BEGIN
            SELECT RAISE(ABORT, 'posted transaction is immutable; create a reversal');
        END;

        CREATE TRIGGER validate_reversal_marker
        BEFORE UPDATE OF reversed_by_id ON transactions
        WHEN OLD.status = 'posted'
        BEGIN
            SELECT CASE WHEN OLD.reversed_by_id IS NOT NULL
                THEN RAISE(ABORT, 'reversal marker is immutable') END;
            SELECT CASE WHEN NEW.reversed_by_id IS NULL OR NOT EXISTS (
                SELECT 1
                FROM transactions r
                JOIN transaction_links l ON l.from_transaction_id = r.id
                WHERE r.id = NEW.reversed_by_id
                    AND r.kind = 'reversal'
                    AND r.status = 'posted'
                    AND l.to_transaction_id = OLD.id
                    AND l.relation = 'reversal_of'
            ) THEN RAISE(ABORT, 'invalid reversal marker') END;
        END;

        CREATE TRIGGER validate_transaction_link_insert
        BEFORE INSERT ON transaction_links
        BEGIN
            SELECT CASE WHEN (
                SELECT status FROM transactions WHERE id = NEW.from_transaction_id
            ) != 'draft' THEN RAISE(ABORT, 'links must be attached before posting') END;
            SELECT CASE WHEN (
                SELECT status FROM transactions WHERE id = NEW.to_transaction_id
            ) != 'posted' THEN RAISE(ABORT, 'link target must be posted') END;
        END;

        CREATE TRIGGER transaction_links_immutable_update
        BEFORE UPDATE ON transaction_links
        BEGIN
            SELECT RAISE(ABORT, 'transaction links are immutable');
        END;

        CREATE TRIGGER transaction_links_immutable_delete
        BEFORE DELETE ON transaction_links
        BEGIN
            SELECT RAISE(ABORT, 'transaction links are immutable');
        END;

        CREATE TRIGGER audit_log_append_only_update
        BEFORE UPDATE ON audit_log
        BEGIN
            SELECT RAISE(ABORT, 'audit log is append-only');
        END;

        CREATE TRIGGER audit_log_append_only_delete
        BEFORE DELETE ON audit_log
        BEGIN
            SELECT RAISE(ABORT, 'audit log is append-only');
        END;
        """,
    ),
)


def _configure(connection: sqlite3.Connection) -> sqlite3.Connection:
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def connect(path: str | Path, *, require_initialized: bool = True) -> sqlite3.Connection:
    database = Path(path)
    if require_initialized and not database.is_file():
        raise DatabaseNotInitializedError(
            f"database does not exist: {database}; run `moneyos init` first"
        )
    connection = _configure(sqlite3.connect(database, isolation_level=None))
    if require_initialized and not is_initialized(connection):
        connection.close()
        raise DatabaseNotInitializedError(f"not an initialized MoneyOS database: {database}")
    return connection


def is_initialized(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
    ).fetchone()
    return row is not None


def initialize(path: str | Path) -> int:
    database = Path(path)
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = _configure(sqlite3.connect(database, isolation_level=None))
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
        applied = {
            row["version"]
            for row in connection.execute("SELECT version FROM schema_migrations").fetchall()
        }
        for migration in MIGRATIONS:
            if migration.version in applied:
                continue
            applied_at = utc_now()
            script = (
                "BEGIN IMMEDIATE;\n"
                + migration.sql
                + "\nINSERT INTO schema_migrations(version, name, applied_at) VALUES "
                + f"({migration.version}, '{migration.name}', '{applied_at}');\nCOMMIT;"
            )
            try:
                connection.executescript(script)
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
        return current_schema_version(connection)
    finally:
        connection.close()


def current_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT coalesce(max(version), 0) AS version FROM schema_migrations").fetchone()
    return int(row["version"])


@contextmanager
def write_transaction(connection: sqlite3.Connection) -> Iterator[None]:
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()


def check_integrity(path: str | Path) -> None:
    connection = connect(path)
    try:
        result = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise ValidationError(f"SQLite integrity check failed: {result}")
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise ValidationError(f"database has {len(violations)} foreign-key violation(s)")
    finally:
        connection.close()


def backup_database(source: str | Path, destination: str | Path) -> Path:
    source_path = Path(source)
    destination_path = Path(destination)
    if destination_path.exists():
        raise ConflictError(f"backup destination already exists: {destination_path}")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    source_connection = connect(source_path)
    destination_connection: sqlite3.Connection | None = None
    try:
        destination_connection = _configure(sqlite3.connect(destination_path))
        source_connection.backup(destination_connection)
    except Exception:
        if destination_connection is not None:
            destination_connection.close()
        destination_path.unlink(missing_ok=True)
        raise
    finally:
        source_connection.close()
        if destination_connection is not None:
            destination_connection.close()
    check_integrity(destination_path)
    return destination_path


def restore_database(source: str | Path, target: str | Path) -> Path:
    source_path = Path(source)
    target_path = Path(target)
    if target_path.exists():
        raise ConflictError(f"restore target already exists: {target_path}")
    check_integrity(source_path)
    return backup_database(source_path, target_path)


def utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
