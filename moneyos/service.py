"""Validated accounting workflows: the only supported ledger write boundary."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from . import db
from .errors import ConflictError, ValidationError
from .models import Account, AccountBalance, Transaction
from .money import normalize_currency
from .repository import LedgerRepository


ACCOUNT_KINDS = {"asset", "liability"}
CATEGORY_KINDS = {"expense", "income"}
TRANSACTION_KINDS = {
    "opening",
    "expense",
    "income",
    "transfer",
    "refund",
    "reimbursement",
    "reversal",
    "adjustment",
}


class LedgerService:
    """Coordinates domain validation, transactions, persistence, and audit records."""

    def __init__(self, database: str | Path):
        self.database = Path(database)

    def initialize(self) -> int:
        return db.initialize(self.database)

    def create_account(
        self,
        name: str,
        *,
        kind: str = "asset",
        currency: str = "CNY",
        opening_minor: int = 0,
        actor: str = "user",
        source: str = "cli",
    ) -> Account:
        name = _name(name, "account name")
        kind = kind.lower()
        if kind not in ACCOUNT_KINDS:
            raise ValidationError("user account kind must be asset or liability")
        currency = normalize_currency(currency)
        if isinstance(opening_minor, bool) or not isinstance(opening_minor, int):
            raise ValidationError("opening balance must be integer minor units")
        if opening_minor < 0:
            raise ValidationError("opening balance cannot be negative; use an adjustment later")
        connection = db.connect(self.database)
        try:
            with db.write_transaction(connection):
                repository = LedgerRepository(connection)
                account = repository.create_account(
                    name=name,
                    kind=kind,
                    role="user",
                    currency=currency,
                    actor=actor,
                    source=source,
                )
                if opening_minor:
                    equity = self._ensure_system_account(
                        repository,
                        name=f"Equity:Opening Balance:{currency}",
                        kind="equity",
                        currency=currency,
                        actor=actor,
                        source=source,
                    )
                    account_posting = opening_minor if kind == "asset" else -opening_minor
                    repository.post_transaction(
                        kind="opening",
                        amount_minor=opening_minor,
                        currency=currency,
                        occurred_on=date.today().isoformat(),
                        description=f"Opening balance for {name}",
                        postings=((account, account_posting, None), (equity, -account_posting, None)),
                        actor=actor,
                        source=source,
                    )
                return account
        finally:
            connection.close()

    def create_category(
        self,
        name: str,
        *,
        kind: str = "expense",
        currency: str = "CNY",
        actor: str = "user",
        source: str = "cli",
    ) -> Account:
        name = _name(name, "category name")
        kind = kind.lower()
        if kind not in CATEGORY_KINDS:
            raise ValidationError("category kind must be expense or income")
        currency = normalize_currency(currency)
        connection = db.connect(self.database)
        try:
            with db.write_transaction(connection):
                return LedgerRepository(connection).create_account(
                    name=name,
                    kind=kind,
                    role="category",
                    currency=currency,
                    actor=actor,
                    source=source,
                )
        finally:
            connection.close()

    def record_expense(
        self,
        *,
        account: str,
        category: str,
        amount_minor: int,
        personal_minor: int | None = None,
        owed_by: str | None = None,
        occurred_on: str | None = None,
        description: str | None = None,
        payee: str | None = None,
        raw_input: str | None = None,
        actor: str = "user",
        source: str = "cli",
    ) -> str:
        _positive(amount_minor)
        personal = amount_minor if personal_minor is None else personal_minor
        if isinstance(personal, bool) or not isinstance(personal, int):
            raise ValidationError("personal amount must be integer minor units")
        if personal < 0 or personal > amount_minor:
            raise ValidationError("personal amount must be between zero and the paid amount")
        owed = amount_minor - personal
        if owed and not owed_by:
            raise ValidationError("owed-by is required when personal amount is less than paid amount")
        if not owed and owed_by:
            raise ValidationError("owed-by requires personal amount to be less than paid amount")
        connection = db.connect(self.database)
        try:
            with db.write_transaction(connection):
                repository = LedgerRepository(connection)
                paid_account = self._require_account(repository, account)
                expense_category = self._require_category(repository, category, "expense")
                self._same_currency(paid_account, expense_category)
                postings: list[tuple[Account, int, str | None]] = [
                    (paid_account, -amount_minor, "merchant payment")
                ]
                if personal:
                    postings.append((expense_category, personal, "personal cost"))
                if owed:
                    party = _name(owed_by or "", "party")
                    receivable = self._ensure_party_account(
                        repository,
                        party=party,
                        currency=paid_account.currency,
                        actor=actor,
                        source=source,
                    )
                    postings.append((receivable, owed, "amount owed to user"))
                return repository.post_transaction(
                    kind="expense",
                    amount_minor=amount_minor,
                    currency=paid_account.currency,
                    occurred_on=_date(occurred_on),
                    description=_description(description, f"{expense_category.name} expense"),
                    payee=_optional_text(payee, "payee", 200),
                    raw_input=_raw_input(raw_input),
                    metadata={"personal_amount_minor": personal, "owed_amount_minor": owed},
                    postings=postings,
                    actor=actor,
                    source=source,
                )
        finally:
            connection.close()

    def record_income(
        self,
        *,
        account: str,
        category: str,
        amount_minor: int,
        occurred_on: str | None = None,
        description: str | None = None,
        payee: str | None = None,
        raw_input: str | None = None,
        actor: str = "user",
        source: str = "cli",
    ) -> str:
        _positive(amount_minor)
        connection = db.connect(self.database)
        try:
            with db.write_transaction(connection):
                repository = LedgerRepository(connection)
                target = self._require_account(repository, account)
                category_account = self._require_category(repository, category, "income")
                self._same_currency(target, category_account)
                return repository.post_transaction(
                    kind="income",
                    amount_minor=amount_minor,
                    currency=target.currency,
                    occurred_on=_date(occurred_on),
                    description=_description(description, f"{category_account.name} income"),
                    payee=_optional_text(payee, "payee", 200),
                    raw_input=_raw_input(raw_input),
                    postings=(
                        (target, amount_minor, "income received"),
                        (category_account, -amount_minor, "income recognized"),
                    ),
                    actor=actor,
                    source=source,
                )
        finally:
            connection.close()

    def record_transfer(
        self,
        *,
        from_account: str,
        to_account: str,
        amount_minor: int,
        occurred_on: str | None = None,
        description: str | None = None,
        raw_input: str | None = None,
        actor: str = "user",
        source: str = "cli",
    ) -> str:
        _positive(amount_minor)
        connection = db.connect(self.database)
        try:
            with db.write_transaction(connection):
                repository = LedgerRepository(connection)
                origin = self._require_account(repository, from_account)
                target = self._require_account(repository, to_account)
                if origin.id == target.id:
                    raise ValidationError("transfer accounts must be different")
                self._same_currency(origin, target)
                return repository.post_transaction(
                    kind="transfer",
                    amount_minor=amount_minor,
                    currency=origin.currency,
                    occurred_on=_date(occurred_on),
                    description=_description(
                        description, f"Transfer from {origin.name} to {target.name}"
                    ),
                    raw_input=_raw_input(raw_input),
                    postings=(
                        (origin, -amount_minor, "transfer out"),
                        (target, amount_minor, "transfer in"),
                    ),
                    actor=actor,
                    source=source,
                )
        finally:
            connection.close()

    def record_refund(
        self,
        *,
        account: str,
        category: str,
        amount_minor: int,
        original_transaction_id: str,
        occurred_on: str | None = None,
        description: str | None = None,
        actor: str = "user",
        source: str = "cli",
    ) -> str:
        _positive(amount_minor)
        connection = db.connect(self.database)
        try:
            with db.write_transaction(connection):
                repository = LedgerRepository(connection)
                original = repository.get_transaction(original_transaction_id)
                if original.kind != "expense":
                    raise ValidationError("a refund must link to an expense transaction")
                if original.reversed_by_id:
                    raise ValidationError("cannot refund an expense that has been reversed")
                target = self._require_account(repository, account)
                expense_category = self._require_category(repository, category, "expense")
                self._same_currency(target, expense_category)
                if original.currency != target.currency:
                    raise ValidationError("refund currency must match the original transaction")
                available = self._remaining_linked_posting(
                    connection,
                    original_transaction_id,
                    expense_category.id,
                    relation="refund_of",
                    reducing_sign=-1,
                )
                if amount_minor > available:
                    raise ValidationError(
                        f"refund exceeds remaining refundable category amount ({available} minor units)"
                    )
                return repository.post_transaction(
                    kind="refund",
                    amount_minor=amount_minor,
                    currency=target.currency,
                    occurred_on=_date(occurred_on),
                    description=_description(description, f"Refund for {original.description}"),
                    postings=(
                        (target, amount_minor, "refund received"),
                        (expense_category, -amount_minor, "expense reduced"),
                    ),
                    links=((original.id, "refund_of"),),
                    actor=actor,
                    source=source,
                )
        finally:
            connection.close()

    def record_reimbursement(
        self,
        *,
        account: str,
        party: str,
        amount_minor: int,
        original_transaction_id: str,
        occurred_on: str | None = None,
        description: str | None = None,
        actor: str = "user",
        source: str = "cli",
    ) -> str:
        _positive(amount_minor)
        party = _name(party, "party")
        connection = db.connect(self.database)
        try:
            with db.write_transaction(connection):
                repository = LedgerRepository(connection)
                original = repository.get_transaction(original_transaction_id)
                if original.kind != "expense":
                    raise ValidationError("a reimbursement must link to an expense transaction")
                if original.reversed_by_id:
                    raise ValidationError("cannot reimburse an expense that has been reversed")
                target = self._require_account(repository, account)
                receivable = repository.find_account(f"Receivable:{party}")
                if receivable is None or receivable.role != "party":
                    raise ValidationError(f"the original expense has no receivable for party: {party}")
                self._same_currency(target, receivable)
                if original.currency != target.currency:
                    raise ValidationError("reimbursement currency must match the original transaction")
                available = self._remaining_linked_posting(
                    connection,
                    original_transaction_id,
                    receivable.id,
                    relation="reimbursement_of",
                    reducing_sign=-1,
                )
                if amount_minor > available:
                    raise ValidationError(
                        f"reimbursement exceeds remaining linked receivable ({available} minor units)"
                    )
                return repository.post_transaction(
                    kind="reimbursement",
                    amount_minor=amount_minor,
                    currency=target.currency,
                    occurred_on=_date(occurred_on),
                    description=_description(description, f"Reimbursement from {party}"),
                    postings=(
                        (target, amount_minor, "reimbursement received"),
                        (receivable, -amount_minor, "receivable settled"),
                    ),
                    links=((original.id, "reimbursement_of"),),
                    actor=actor,
                    source=source,
                )
        finally:
            connection.close()

    def reverse_transaction(
        self,
        transaction_id: str,
        *,
        reason: str,
        occurred_on: str | None = None,
        actor: str = "user",
        source: str = "cli",
    ) -> str:
        reason = _name(reason, "reversal reason")
        connection = db.connect(self.database)
        try:
            with db.write_transaction(connection):
                repository = LedgerRepository(connection)
                original = repository.get_transaction(transaction_id)
                if original.reversed_by_id:
                    raise ConflictError(
                        f"transaction already reversed by {original.reversed_by_id}"
                    )
                if original.kind == "reversal":
                    raise ValidationError("reversing a reversal is not supported in V0.1")
                active_dependents = connection.execute(
                    """
                    SELECT count(*)
                    FROM transaction_links l
                    JOIN transactions child ON child.id = l.from_transaction_id
                    WHERE l.to_transaction_id = ? AND child.reversed_by_id IS NULL
                    """,
                    (original.id,),
                ).fetchone()[0]
                if active_dependents:
                    raise ConflictError(
                        "reverse linked refunds/reimbursements before reversing the original transaction"
                    )
                reversal_id = repository.post_transaction(
                    kind="reversal",
                    amount_minor=original.amount_minor,
                    currency=original.currency,
                    occurred_on=_date(occurred_on),
                    description=f"Reversal: {original.description}",
                    metadata={"reason": reason},
                    postings=tuple(
                        (
                            repository.get_account(posting.account_id),
                            -posting.amount_minor,
                            f"reverses {transaction_id}",
                        )
                        for posting in original.postings
                    ),
                    links=((original.id, "reversal_of"),),
                    actor=actor,
                    source=source,
                )
                repository.set_reversed_by(original.id, reversal_id)
                repository.append_audit(
                    action="mark_reversed",
                    entity_type="transaction",
                    entity_id=original.id,
                    actor=actor,
                    source=source,
                    reason=reason,
                    before={"reversed_by_id": None},
                    after={"reversed_by_id": reversal_id},
                )
                return reversal_id
        finally:
            connection.close()

    def accounts(self, *, role: str | None = None) -> list[Account]:
        connection = db.connect(self.database)
        try:
            return LedgerRepository(connection).list_accounts(role=role)
        finally:
            connection.close()

    def balances(self, *, role: str | None = None) -> list[AccountBalance]:
        connection = db.connect(self.database)
        try:
            return LedgerRepository(connection).balances(role=role)
        finally:
            connection.close()

    def transactions(self, *, limit: int = 50, kind: str | None = None) -> list[Transaction]:
        if limit < 1 or limit > 1000:
            raise ValidationError("limit must be between 1 and 1000")
        if kind is not None and kind not in TRANSACTION_KINDS:
            raise ValidationError(f"unknown transaction kind: {kind}")
        connection = db.connect(self.database)
        try:
            return LedgerRepository(connection).list_transactions(limit=limit, kind=kind)
        finally:
            connection.close()

    def transaction(self, transaction_id: str) -> Transaction:
        connection = db.connect(self.database)
        try:
            return LedgerRepository(connection).get_transaction(transaction_id)
        finally:
            connection.close()

    def audit(self, *, limit: int = 100) -> list[dict[str, Any]]:
        if limit < 1 or limit > 1000:
            raise ValidationError("limit must be between 1 and 1000")
        connection = db.connect(self.database)
        try:
            return LedgerRepository(connection).list_audit(limit=limit)
        finally:
            connection.close()

    @staticmethod
    def _require_account(repository: LedgerRepository, reference: str) -> Account:
        account = repository.get_account(reference)
        if account.role != "user" or account.kind not in ACCOUNT_KINDS:
            raise ValidationError(f"not a user asset/liability account: {reference}")
        if account.archived:
            raise ValidationError(f"account is archived: {reference}")
        return account

    @staticmethod
    def _require_category(repository: LedgerRepository, reference: str, kind: str) -> Account:
        account = repository.get_account(reference)
        if account.role != "category" or account.kind != kind:
            raise ValidationError(f"not an {kind} category: {reference}")
        if account.archived:
            raise ValidationError(f"category is archived: {reference}")
        return account

    @staticmethod
    def _same_currency(first: Account, second: Account) -> None:
        if first.currency != second.currency:
            raise ValidationError(
                f"currency mismatch: {first.name} is {first.currency}, "
                f"{second.name} is {second.currency}"
            )

    @staticmethod
    def _ensure_system_account(
        repository: LedgerRepository,
        *,
        name: str,
        kind: str,
        currency: str,
        actor: str,
        source: str,
    ) -> Account:
        existing = repository.find_account(name)
        if existing:
            if existing.role != "system" or existing.kind != kind or existing.currency != currency:
                raise ConflictError(f"reserved system account name is already in use: {name}")
            return existing
        return repository.create_account(
            name=name,
            kind=kind,
            role="system",
            currency=currency,
            actor=actor,
            source=source,
        )

    @staticmethod
    def _ensure_party_account(
        repository: LedgerRepository,
        *,
        party: str,
        currency: str,
        actor: str,
        source: str,
    ) -> Account:
        name = f"Receivable:{party}"
        existing = repository.find_account(name)
        if existing:
            if (
                existing.role != "party"
                or existing.kind != "receivable"
                or existing.currency != currency
            ):
                raise ConflictError(f"reserved receivable account name is already in use: {name}")
            return existing
        return repository.create_account(
            name=name,
            kind="receivable",
            role="party",
            currency=currency,
            actor=actor,
            source=source,
        )

    @staticmethod
    def _remaining_linked_posting(
        connection,
        original_id: str,
        account_id: str,
        *,
        relation: str,
        reducing_sign: int,
    ) -> int:
        original_row = connection.execute(
            """
            SELECT coalesce(sum(amount_minor), 0) AS amount
            FROM postings WHERE transaction_id = ? AND account_id = ?
            """,
            (original_id, account_id),
        ).fetchone()
        original_amount = int(original_row["amount"])
        linked_row = connection.execute(
            """
            SELECT coalesce(sum(p.amount_minor), 0) AS amount
            FROM transaction_links l
            JOIN postings p ON p.transaction_id = l.from_transaction_id
            JOIN transactions t ON t.id = p.transaction_id AND t.status = 'posted'
            WHERE l.to_transaction_id = ? AND l.relation = ? AND p.account_id = ?
                AND t.reversed_by_id IS NULL
            """,
            (original_id, relation, account_id),
        ).fetchone()
        linked_amount = int(linked_row["amount"])
        remaining = original_amount + (linked_amount if reducing_sign < 0 else -linked_amount)
        return max(remaining, 0)


def _positive(amount_minor: int) -> None:
    if isinstance(amount_minor, bool) or not isinstance(amount_minor, int) or amount_minor <= 0:
        raise ValidationError("amount must be a positive integer number of minor units")


def _date(value: str | None) -> str:
    if value is None:
        return date.today().isoformat()
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValidationError("date must use YYYY-MM-DD format") from None
    if parsed.isoformat() != value:
        raise ValidationError("date must use YYYY-MM-DD format")
    return value


def _name(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValidationError(f"{label} cannot be empty")
    if len(normalized) > 200:
        raise ValidationError(f"{label} cannot exceed 200 characters")
    return normalized


def _optional_text(value: str | None, label: str, limit: int) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if len(stripped) > limit:
        raise ValidationError(f"{label} cannot exceed {limit} characters")
    return stripped or None


def _description(value: str | None, default: str) -> str:
    return _optional_text(value, "description", 500) or default


def _raw_input(value: str | None) -> str | None:
    if value is None:
        return None
    if len(value) > 100_000:
        raise ValidationError("raw input cannot exceed 100000 characters")
    return value
