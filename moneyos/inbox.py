"""Raw inbox orchestration, parsing, review, and idempotent ledger confirmation."""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import db
from .errors import ConflictError, ValidationError
from .inbox_repository import InboxRepository
from .models import RawMessage, Transaction, TransactionProposal
from .parser import DeterministicParser, ParseError, ParserContext, TransactionParser
from .service import LedgerService


MESSAGE_STATUSES = {"pending", "proposed", "confirmed", "rejected", "failed"}


@dataclass(frozen=True)
class ParseBatchResult:
    proposals: tuple[TransactionProposal, ...]
    failures: tuple[tuple[str, str], ...]


class InboxService:
    def __init__(
        self,
        database: str | Path,
        *,
        parser: TransactionParser | None = None,
    ):
        self.database = Path(database)
        self.parser = parser or DeterministicParser()
        self.ledger = LedgerService(database)

    def ingest(
        self,
        content: str,
        *,
        channel: str = "cli",
        external_id: str | None = None,
        actor: str = "user",
        source: str = "cli",
    ) -> tuple[RawMessage, bool]:
        channel = _bounded(channel, "channel", 100)
        if not isinstance(content, str) or not content.strip():
            raise ValidationError("message content cannot be empty")
        if len(content) > 100_000:
            raise ValidationError("message content cannot exceed 100000 characters")
        if external_id is not None:
            external_id = _bounded(external_id, "external ID", 500)
        connection = db.connect(self.database)
        try:
            with db.write_transaction(connection):
                return InboxRepository(connection).ingest(
                    channel=channel,
                    content=content,
                    external_id=external_id,
                    actor=actor,
                    source=source,
                )
        finally:
            connection.close()

    def parse_message(
        self,
        message_id: str,
        *,
        actor: str = "system",
        source: str = "parser",
    ) -> TransactionProposal:
        message = self.message(message_id)
        if message.status not in {"pending", "failed"}:
            raise ConflictError(f"message in {message.status!r} state cannot be parsed")
        try:
            result = self.parser.parse(message.content, context=self._parser_context())
            self._validate_parse_result(result.kind, result.payload, result.confidence)
        except (ParseError, ValidationError) as error:
            self._mark_failed(message, str(error), actor=actor, source=source)
            raise
        except Exception as error:
            safe_error = f"parser {self.parser.parser_id} failed: {type(error).__name__}"
            self._mark_failed(message, safe_error, actor=actor, source=source)
            raise ParseError(safe_error) from error

        connection = db.connect(self.database)
        try:
            with db.write_transaction(connection):
                current = InboxRepository(connection).get_message(message.id)
                if current.status not in {"pending", "failed"}:
                    raise ConflictError(f"message in {current.status!r} state cannot be parsed")
                return InboxRepository(connection).create_proposal(
                    message=current,
                    result=result,
                    actor=actor,
                    source=source,
                )
        finally:
            connection.close()

    def parse_pending(
        self,
        *,
        limit: int = 50,
        actor: str = "system",
        source: str = "parser",
    ) -> ParseBatchResult:
        _limit(limit)
        connection = db.connect(self.database)
        try:
            candidates = InboxRepository(connection).parse_candidates(limit=limit)
        finally:
            connection.close()
        proposals: list[TransactionProposal] = []
        failures: list[tuple[str, str]] = []
        for message in candidates:
            try:
                proposals.append(self.parse_message(message.id, actor=actor, source=source))
            except (ParseError, ConflictError, ValidationError) as error:
                failures.append((message.id, str(error)))
        return ParseBatchResult(tuple(proposals), tuple(failures))

    def confirm(
        self,
        proposal_id: str,
        *,
        account: str | None = None,
        category: str | None = None,
        from_account: str | None = None,
        to_account: str | None = None,
        owed_by: str | None = None,
        occurred_on: str | None = None,
        description: str | None = None,
        reviewer: str = "user",
        source: str = "cli",
    ) -> str:
        proposal, message = self.proposal_with_message(proposal_id)
        if proposal.status == "confirmed":
            if proposal.transaction_id is None:
                raise ConflictError("confirmed proposal is missing its transaction reference")
            return proposal.transaction_id
        if proposal.status != "proposed":
            raise ConflictError(f"proposal in {proposal.status!r} state cannot be confirmed")

        transaction = self.ledger.transaction_for_raw_message(message.id)
        if transaction is None:
            try:
                transaction_id = self._post_primary(
                    proposal,
                    message,
                    account=account,
                    category=category,
                    from_account=from_account,
                    to_account=to_account,
                    owed_by=owed_by,
                    occurred_on=occurred_on,
                    description=description,
                    reviewer=reviewer,
                )
            except sqlite3.IntegrityError:
                recovered = self.ledger.transaction_for_raw_message(message.id)
                if recovered is None:
                    raise
                self._validate_recovered_transaction(proposal, message, recovered)
                transaction_id = recovered.id
        else:
            self._validate_recovered_transaction(proposal, message, transaction)
            transaction_id = transaction.id

        settled_minor = int(proposal.payload.get("settled_minor", 0))
        if settled_minor:
            party = owed_by or proposal.payload.get("owed_by")
            if not party:
                raise ValidationError("owed-by is required for the detected reimbursement")
            target_account = account or proposal.payload.get("account")
            if not target_account:
                raise ValidationError("account is required for the detected reimbursement")
            self._ensure_settlement(
                original_transaction_id=transaction_id,
                account=str(target_account),
                party=str(party),
                settled_minor=settled_minor,
                reviewer=reviewer,
                source=f"inbox:{message.channel}",
            )

        connection = db.connect(self.database)
        try:
            with db.write_transaction(connection):
                repository = InboxRepository(connection)
                current = repository.get_proposal(proposal.id)
                if current.status == "confirmed":
                    if current.transaction_id != transaction_id:
                        raise ConflictError("proposal was confirmed with another transaction")
                    return transaction_id
                repository.confirm(
                    proposal=current,
                    transaction_id=transaction_id,
                    reviewer=reviewer,
                    source=source,
                )
        finally:
            connection.close()
        return transaction_id

    def reject(
        self,
        proposal_id: str,
        *,
        reason: str,
        reviewer: str = "user",
        source: str = "cli",
    ) -> None:
        reason = _bounded(reason, "rejection reason", 500)
        connection = db.connect(self.database)
        try:
            with db.write_transaction(connection):
                repository = InboxRepository(connection)
                proposal = repository.get_proposal(proposal_id)
                if proposal.status == "rejected":
                    return
                if proposal.status != "proposed":
                    raise ConflictError(
                        f"proposal in {proposal.status!r} state cannot be rejected"
                    )
                repository.reject(
                    proposal=proposal,
                    reason=reason,
                    reviewer=reviewer,
                    source=source,
                )
        finally:
            connection.close()

    def message(self, message_id: str) -> RawMessage:
        connection = db.connect(self.database)
        try:
            return InboxRepository(connection).get_message(message_id)
        finally:
            connection.close()

    def messages(self, *, status: str | None = None, limit: int = 100) -> list[RawMessage]:
        _limit(limit)
        if status is not None and status not in MESSAGE_STATUSES:
            raise ValidationError(f"unknown inbox status: {status}")
        connection = db.connect(self.database)
        try:
            return InboxRepository(connection).list_messages(status=status, limit=limit)
        finally:
            connection.close()

    def proposal(self, proposal_id: str) -> TransactionProposal:
        connection = db.connect(self.database)
        try:
            return InboxRepository(connection).get_proposal(proposal_id)
        finally:
            connection.close()

    def proposal_with_message(
        self, proposal_id: str
    ) -> tuple[TransactionProposal, RawMessage]:
        connection = db.connect(self.database)
        try:
            repository = InboxRepository(connection)
            proposal = repository.get_proposal(proposal_id)
            return proposal, repository.get_message(proposal.raw_message_id)
        finally:
            connection.close()

    def proposals_for_message(self, message_id: str) -> list[TransactionProposal]:
        connection = db.connect(self.database)
        try:
            repository = InboxRepository(connection)
            repository.get_message(message_id)
            return repository.proposals_for_message(message_id)
        finally:
            connection.close()

    def _post_primary(
        self,
        proposal: TransactionProposal,
        message: RawMessage,
        *,
        account: str | None,
        category: str | None,
        from_account: str | None,
        to_account: str | None,
        owed_by: str | None,
        occurred_on: str | None,
        description: str | None,
        reviewer: str,
    ) -> str:
        payload = proposal.payload
        source = f"inbox:{message.channel}"
        final_description = description or payload.get("description")
        if proposal.kind == "expense":
            final_account = account or payload.get("account")
            final_category = category or payload.get("category")
            if not final_account or not final_category:
                raise ValidationError("expense confirmation requires account and category")
            return self.ledger.record_expense(
                account=str(final_account),
                category=str(final_category),
                amount_minor=_payload_minor(payload, "amount_minor"),
                personal_minor=_optional_payload_minor(payload, "personal_minor"),
                owed_by=owed_by or payload.get("owed_by"),
                occurred_on=occurred_on,
                description=final_description,
                payee=payload.get("payee"),
                raw_input=message.content,
                raw_message_id=message.id,
                actor=reviewer,
                source=source,
            )
        if proposal.kind == "income":
            final_account = account or payload.get("account")
            final_category = category or payload.get("category")
            if not final_account or not final_category:
                raise ValidationError("income confirmation requires account and category")
            return self.ledger.record_income(
                account=str(final_account),
                category=str(final_category),
                amount_minor=_payload_minor(payload, "amount_minor"),
                occurred_on=occurred_on,
                description=final_description,
                payee=payload.get("payee"),
                raw_input=message.content,
                raw_message_id=message.id,
                actor=reviewer,
                source=source,
            )
        if proposal.kind == "transfer":
            origin = from_account or payload.get("from_account")
            target = to_account or payload.get("to_account")
            if not origin or not target:
                raise ValidationError("transfer confirmation requires from and to accounts")
            return self.ledger.record_transfer(
                from_account=str(origin),
                to_account=str(target),
                amount_minor=_payload_minor(payload, "amount_minor"),
                occurred_on=occurred_on,
                description=final_description,
                raw_input=message.content,
                raw_message_id=message.id,
                actor=reviewer,
                source=source,
            )
        raise ValidationError(f"unsupported proposal kind: {proposal.kind}")

    def _ensure_settlement(
        self,
        *,
        original_transaction_id: str,
        account: str,
        party: str,
        settled_minor: int,
        reviewer: str,
        source: str,
    ) -> None:
        connection = db.connect(self.database)
        try:
            existing = int(connection.execute(
                """
                SELECT coalesce(sum(child.amount_minor), 0)
                FROM transaction_links link
                JOIN transactions child ON child.id = link.from_transaction_id
                WHERE link.to_transaction_id = ?
                    AND link.relation = 'reimbursement_of'
                    AND child.status = 'posted'
                    AND child.reversed_by_id IS NULL
                """,
                (original_transaction_id,),
            ).fetchone()[0])
        finally:
            connection.close()
        if existing > settled_minor:
            raise ConflictError("linked reimbursements exceed the parsed settlement amount")
        remaining = settled_minor - existing
        if remaining:
            self.ledger.record_reimbursement(
                account=account,
                party=party,
                amount_minor=remaining,
                original_transaction_id=original_transaction_id,
                description="Reimbursement captured from the same inbox message",
                actor=reviewer,
                source=source,
            )

    @staticmethod
    def _validate_recovered_transaction(
        proposal: TransactionProposal,
        message: RawMessage,
        transaction: Transaction,
    ) -> None:
        expected_amount = _payload_minor(proposal.payload, "amount_minor")
        if transaction.kind != proposal.kind or transaction.amount_minor != expected_amount:
            raise ConflictError(
                "raw message is already linked to a transaction that does not match the proposal"
            )
        if transaction.raw_input != message.content:
            raise ConflictError("linked transaction does not preserve the same raw message content")
        if proposal.kind == "expense":
            expected_personal = proposal.payload.get("personal_minor", expected_amount)
            actual_personal = (transaction.metadata or {}).get("personal_amount_minor")
            if actual_personal != expected_personal:
                raise ConflictError(
                    "linked expense does not match the proposal's personal amount"
                )

    def _mark_failed(
        self,
        message: RawMessage,
        error: str,
        *,
        actor: str,
        source: str,
    ) -> None:
        connection = db.connect(self.database)
        try:
            with db.write_transaction(connection):
                repository = InboxRepository(connection)
                current = repository.get_message(message.id)
                if current.status not in {"pending", "failed"}:
                    return
                repository.mark_parse_failed(
                    message=current,
                    error=error[:1000],
                    parser_id=self.parser.parser_id,
                    parser_version=self.parser.parser_version,
                    model_id=self.parser.model_id,
                    actor=actor,
                    source=source,
                )
        finally:
            connection.close()

    def _parser_context(self) -> ParserContext:
        accounts = self.ledger.accounts(role="user")
        categories = self.ledger.accounts(role="category")
        return ParserContext(
            default_currency="CNY",
            accounts=tuple(item.name for item in accounts),
            expense_categories=tuple(item.name for item in categories if item.kind == "expense"),
            income_categories=tuple(item.name for item in categories if item.kind == "income"),
        )

    @staticmethod
    def _validate_parse_result(kind: str, payload: dict[str, Any], confidence: float) -> None:
        if kind not in {"expense", "income", "transfer"}:
            raise ParseError(f"parser returned unsupported transaction kind: {kind}")
        if not isinstance(payload, dict):
            raise ParseError("parser payload must be an object")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ParseError("parser confidence must be numeric")
        if not math.isfinite(confidence) or confidence < 0 or confidence > 1:
            raise ParseError("parser confidence must be between zero and one")
        amount = _payload_minor(payload, "amount_minor")
        if kind == "expense":
            personal = _optional_payload_minor(payload, "personal_minor")
            if personal is not None and personal > amount:
                raise ParseError("proposal personal amount cannot exceed paid amount")
            settled = _optional_payload_minor(payload, "settled_minor")
            if settled is not None and settled > amount - (personal if personal is not None else amount):
                raise ParseError("proposal settlement cannot exceed its receivable")
        try:
            json.dumps(payload, ensure_ascii=False)
        except (TypeError, ValueError):
            raise ParseError("parser payload must be JSON serializable") from None


def _payload_minor(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValidationError(f"proposal {key} must be positive integer minor units")
    return value


def _optional_payload_minor(payload: dict[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValidationError(f"proposal {key} must be non-negative integer minor units")
    return value


def _bounded(value: str, label: str, limit: int) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{label} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValidationError(f"{label} cannot be empty")
    if len(normalized) > limit:
        raise ValidationError(f"{label} cannot exceed {limit} characters")
    return normalized


def _limit(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > 1000:
        raise ValidationError("limit must be between 1 and 1000")
