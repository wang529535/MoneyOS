"""Explicit SQL persistence for the MoneyOS ledger."""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any, Iterable

from .db import utc_now
from .errors import ConflictError, NotFoundError
from .models import Account, AccountBalance, Posting, Transaction


NORMAL_DEBIT_KINDS = {"asset", "expense", "receivable"}


class LedgerRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def create_account(
        self,
        *,
        name: str,
        kind: str,
        role: str,
        currency: str,
        actor: str,
        source: str,
    ) -> Account:
        account_id = str(uuid.uuid4())
        created_at = utc_now()
        try:
            self.connection.execute(
                """
                INSERT INTO accounts(id, name, kind, role, currency, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (account_id, name, kind, role, currency, created_at),
            )
        except sqlite3.IntegrityError as error:
            if "UNIQUE" in str(error):
                raise ConflictError(f"account or category already exists: {name}") from None
            raise
        account = Account(account_id, name, kind, role, currency, False, created_at)
        self.append_audit(
            action="create",
            entity_type="account",
            entity_id=account_id,
            actor=actor,
            source=source,
            after=account.__dict__,
        )
        return account

    def get_account(self, reference: str) -> Account:
        row = self.connection.execute(
            "SELECT * FROM accounts WHERE id = ?",
            (reference,),
        ).fetchone()
        if row is None:
            row = self.connection.execute(
                "SELECT * FROM accounts WHERE name = ? COLLATE NOCASE",
                (reference,),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"account or category not found: {reference}")
        return _account(row)

    def find_account(self, name: str) -> Account | None:
        row = self.connection.execute(
            "SELECT * FROM accounts WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        return _account(row) if row else None

    def list_accounts(self, *, role: str | None = None, include_archived: bool = False) -> list[Account]:
        clauses: list[str] = []
        params: list[Any] = []
        if role:
            clauses.append("role = ?")
            params.append(role)
        if not include_archived:
            clauses.append("archived = 0")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.connection.execute(
            f"SELECT * FROM accounts{where} ORDER BY role, name COLLATE NOCASE", params
        ).fetchall()
        return [_account(row) for row in rows]

    def balances(self, *, role: str | None = None) -> list[AccountBalance]:
        clauses = ["a.archived = 0"]
        params: list[Any] = []
        if role:
            clauses.append("a.role = ?")
            params.append(role)
        rows = self.connection.execute(
            f"""
            SELECT a.*, coalesce(sum(pp.amount_minor), 0) AS raw_minor
            FROM accounts a
            LEFT JOIN posted_postings pp ON pp.account_id = a.id
            WHERE {' AND '.join(clauses)}
            GROUP BY a.id
            ORDER BY a.role, a.name COLLATE NOCASE
            """,
            params,
        ).fetchall()
        result = []
        for row in rows:
            account = _account(row)
            raw = int(row["raw_minor"])
            normal = raw if account.kind in NORMAL_DEBIT_KINDS else -raw
            result.append(AccountBalance(account, raw, normal))
        return result

    def post_transaction(
        self,
        *,
        kind: str,
        amount_minor: int,
        currency: str,
        occurred_on: str,
        description: str,
        postings: Iterable[tuple[Account, int, str | None]],
        actor: str,
        source: str,
        payee: str | None = None,
        raw_input: str | None = None,
        metadata: dict[str, Any] | None = None,
        links: Iterable[tuple[str, str]] = (),
    ) -> str:
        transaction_id = str(uuid.uuid4())
        created_at = utc_now()
        metadata = metadata or {}
        posting_list = list(postings)
        self.connection.execute(
            """
            INSERT INTO transactions(
                id, kind, amount_minor, currency, occurred_on, description, payee,
                raw_input, actor, source, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                transaction_id,
                kind,
                amount_minor,
                currency,
                occurred_on,
                description,
                payee,
                raw_input,
                actor,
                source,
                json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                created_at,
            ),
        )
        for account, amount, memo in posting_list:
            self.connection.execute(
                "INSERT INTO postings(transaction_id, account_id, amount_minor, memo) VALUES (?, ?, ?, ?)",
                (transaction_id, account.id, amount, memo),
            )
        for related_id, relation in links:
            self.connection.execute(
                """
                INSERT INTO transaction_links(from_transaction_id, to_transaction_id, relation)
                VALUES (?, ?, ?)
                """,
                (transaction_id, related_id, relation),
            )
        self.connection.execute(
            "UPDATE transactions SET status = 'posted' WHERE id = ?", (transaction_id,)
        )
        snapshot = {
            "id": transaction_id,
            "kind": kind,
            "amount_minor": amount_minor,
            "currency": currency,
            "occurred_on": occurred_on,
            "description": description,
            "payee": payee,
            "postings": [
                {"account_id": account.id, "account_name": account.name, "amount_minor": amount}
                for account, amount, _ in posting_list
            ],
            "links": [{"to": related_id, "relation": relation} for related_id, relation in links],
        }
        self.append_audit(
            action="post",
            entity_type="transaction",
            entity_id=transaction_id,
            actor=actor,
            source=source,
            after=snapshot,
        )
        return transaction_id

    def get_transaction(self, transaction_id: str) -> Transaction:
        row = self.connection.execute(
            "SELECT * FROM transactions WHERE id = ? AND status = 'posted'", (transaction_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"transaction not found: {transaction_id}")
        posting_rows = self.connection.execute(
            """
            SELECT p.*, a.name AS account_name
            FROM postings p JOIN accounts a ON a.id = p.account_id
            WHERE p.transaction_id = ? ORDER BY p.id
            """,
            (transaction_id,),
        ).fetchall()
        link_rows = self.connection.execute(
            """
            SELECT from_transaction_id, to_transaction_id, relation
            FROM transaction_links
            WHERE from_transaction_id = ? OR to_transaction_id = ?
            ORDER BY relation
            """,
            (transaction_id, transaction_id),
        ).fetchall()
        postings = tuple(
            Posting(
                int(item["id"]),
                item["transaction_id"],
                item["account_id"],
                item["account_name"],
                int(item["amount_minor"]),
                item["memo"],
            )
            for item in posting_rows
        )
        related = tuple(dict(item) for item in link_rows)
        return _transaction(row, postings=postings, related=related)

    def list_transactions(self, *, limit: int = 50, kind: str | None = None) -> list[Transaction]:
        if kind:
            rows = self.connection.execute(
                """
                SELECT * FROM transactions
                WHERE status = 'posted' AND kind = ?
                ORDER BY occurred_on DESC, created_at DESC LIMIT ?
                """,
                (kind, limit),
            ).fetchall()
        else:
            rows = self.connection.execute(
                """
                SELECT * FROM transactions WHERE status = 'posted'
                ORDER BY occurred_on DESC, created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_transaction(row) for row in rows]

    def set_reversed_by(self, original_id: str, reversal_id: str) -> None:
        self.connection.execute(
            "UPDATE transactions SET reversed_by_id = ? WHERE id = ?",
            (reversal_id, original_id),
        )

    def list_audit(self, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]

    def append_audit(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str,
        actor: str,
        source: str,
        reason: str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO audit_log(
                action, entity_type, entity_id, actor, source, reason,
                before_json, after_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                action,
                entity_type,
                entity_id,
                actor,
                source,
                reason,
                json.dumps(before, ensure_ascii=False, sort_keys=True) if before else None,
                json.dumps(after, ensure_ascii=False, sort_keys=True) if after else None,
                utc_now(),
            ),
        )


def _account(row: sqlite3.Row) -> Account:
    return Account(
        row["id"],
        row["name"],
        row["kind"],
        row["role"],
        row["currency"],
        bool(row["archived"]),
        row["created_at"],
    )


def _transaction(
    row: sqlite3.Row,
    *,
    postings: tuple[Posting, ...] = (),
    related: tuple[dict[str, str], ...] = (),
) -> Transaction:
    return Transaction(
        id=row["id"],
        kind=row["kind"],
        amount_minor=int(row["amount_minor"]),
        currency=row["currency"],
        occurred_on=row["occurred_on"],
        description=row["description"],
        payee=row["payee"],
        status=row["status"],
        raw_input=row["raw_input"],
        actor=row["actor"],
        source=row["source"],
        created_at=row["created_at"],
        reversed_by_id=row["reversed_by_id"],
        related=related,
        postings=postings,
        metadata=json.loads(row["metadata_json"]),
    )
