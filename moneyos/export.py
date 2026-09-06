"""Read-only, deterministic exports of posted ledger facts."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .db import connect, current_schema_version, utc_now
from .errors import ConflictError, ValidationError


def export_database(database: str | Path, output: str | Path, *, format: str) -> Path:
    output_path = Path(output)
    if output_path.exists():
        raise ConflictError(f"export destination already exists: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    normalized = format.lower()
    if normalized == "json":
        _export_json(database, output_path)
    elif normalized == "csv":
        _export_csv(database, output_path)
    else:
        raise ValidationError("export format must be json or csv")
    return output_path


def _export_json(database: str | Path, output: Path) -> None:
    connection = connect(database)
    try:
        payload = {
            "format": "moneyos-ledger-export-v1",
            "exported_at": utc_now(),
            "schema_version": current_schema_version(connection),
            "accounts": [dict(row) for row in connection.execute(
                "SELECT * FROM accounts ORDER BY created_at, id"
            )],
            "transactions": [dict(row) for row in connection.execute(
                "SELECT * FROM transactions WHERE status = 'posted' ORDER BY occurred_on, created_at, id"
            )],
            "postings": [dict(row) for row in connection.execute(
                """
                SELECT p.* FROM postings p JOIN transactions t ON t.id = p.transaction_id
                WHERE t.status = 'posted' ORDER BY p.id
                """
            )],
            "transaction_links": [dict(row) for row in connection.execute(
                "SELECT * FROM transaction_links ORDER BY from_transaction_id, relation"
            )],
            "raw_messages": [dict(row) for row in connection.execute(
                "SELECT * FROM raw_messages ORDER BY received_at, id"
            )],
            "transaction_proposals": [dict(row) for row in connection.execute(
                "SELECT * FROM transaction_proposals ORDER BY created_at, id"
            )],
            "audit_log": [dict(row) for row in connection.execute(
                "SELECT * FROM audit_log ORDER BY id"
            )],
        }
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    finally:
        connection.close()


def _export_csv(database: str | Path, output: Path) -> None:
    connection = connect(database)
    try:
        rows = connection.execute(
            """
            SELECT
                t.id AS transaction_id,
                t.occurred_on,
                t.kind,
                t.amount_minor AS transaction_amount_minor,
                t.currency,
                t.description,
                t.payee,
                t.reversed_by_id,
                p.id AS posting_id,
                a.id AS account_id,
                a.name AS account_name,
                a.kind AS account_kind,
                a.role AS account_role,
                p.amount_minor AS posting_amount_minor,
                p.memo
            FROM transactions t
            JOIN postings p ON p.transaction_id = t.id
            JOIN accounts a ON a.id = p.account_id
            WHERE t.status = 'posted'
            ORDER BY t.occurred_on, t.created_at, p.id
            """
        ).fetchall()
        fieldnames = [
            "transaction_id",
            "occurred_on",
            "kind",
            "transaction_amount_minor",
            "currency",
            "description",
            "payee",
            "reversed_by_id",
            "posting_id",
            "account_id",
            "account_name",
            "account_kind",
            "account_role",
            "posting_amount_minor",
            "memo",
        ]
        with output.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(dict(row) for row in rows)
    finally:
        connection.close()
