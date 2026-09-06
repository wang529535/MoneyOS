"""Persistence operations for raw messages and transaction proposals."""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from .db import utc_now
from .errors import ConflictError, NotFoundError
from .models import RawMessage, TransactionProposal
from .parser import ParseResult
from .repository import LedgerRepository


class InboxRepository:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def ingest(
        self,
        *,
        channel: str,
        content: str,
        external_id: str | None,
        actor: str,
        source: str,
    ) -> tuple[RawMessage, bool]:
        if external_id is not None:
            existing = self.connection.execute(
                "SELECT * FROM raw_messages WHERE channel = ? AND external_id = ?",
                (channel, external_id),
            ).fetchone()
            if existing:
                message = _raw_message(existing)
                if message.content != content:
                    raise ConflictError(
                        "channel/external-id already exists with different content"
                    )
                return message, False
        message_id = str(uuid.uuid4())
        received_at = utc_now()
        self.connection.execute(
            """
            INSERT INTO raw_messages(id, channel, external_id, received_at, content)
            VALUES (?, ?, ?, ?, ?)
            """,
            (message_id, channel, external_id, received_at, content),
        )
        message = RawMessage(
            message_id,
            channel,
            external_id,
            received_at,
            content,
            "pending",
            None,
            None,
            None,
            None,
            None,
        )
        LedgerRepository(self.connection).append_audit(
            action="ingest",
            entity_type="raw_message",
            entity_id=message_id,
            actor=actor,
            source=source,
            after={
                "id": message_id,
                "channel": channel,
                "external_id": external_id,
                "content": content,
                "status": "pending",
            },
        )
        return message, True

    def get_message(self, message_id: str) -> RawMessage:
        row = self.connection.execute(
            "SELECT * FROM raw_messages WHERE id = ?", (message_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"raw message not found: {message_id}")
        return _raw_message(row)

    def list_messages(self, *, status: str | None = None, limit: int = 100) -> list[RawMessage]:
        if status:
            rows = self.connection.execute(
                """
                SELECT * FROM raw_messages WHERE status = ?
                ORDER BY received_at, id LIMIT ?
                """,
                (status, limit),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT * FROM raw_messages ORDER BY received_at, id LIMIT ?", (limit,)
            ).fetchall()
        return [_raw_message(row) for row in rows]

    def parse_candidates(self, *, limit: int) -> list[RawMessage]:
        rows = self.connection.execute(
            """
            SELECT * FROM raw_messages WHERE status = 'pending'
            ORDER BY received_at, id LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [_raw_message(row) for row in rows]

    def create_proposal(
        self,
        *,
        message: RawMessage,
        result: ParseResult,
        actor: str,
        source: str,
    ) -> TransactionProposal:
        current = self.connection.execute(
            """
            SELECT 1 FROM transaction_proposals
            WHERE raw_message_id = ? AND status = 'proposed'
            """,
            (message.id,),
        ).fetchone()
        if current:
            raise ConflictError("raw message already has an active proposal")
        attempt = int(self.connection.execute(
            "SELECT coalesce(max(attempt), 0) + 1 FROM transaction_proposals WHERE raw_message_id = ?",
            (message.id,),
        ).fetchone()[0])
        proposal_id = str(uuid.uuid4())
        created_at = utc_now()
        confidence_ppm = round(result.confidence * 1_000_000)
        self.connection.execute(
            """
            INSERT INTO transaction_proposals(
                id, raw_message_id, attempt, kind, payload_json, confidence_ppm,
                requires_confirmation, parser_id, parser_version, model_id,
                rationale, missing_fields_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal_id,
                message.id,
                attempt,
                result.kind,
                json.dumps(result.payload, ensure_ascii=False, sort_keys=True),
                confidence_ppm,
                int(result.requires_confirmation),
                result.parser_id,
                result.parser_version,
                result.model_id,
                result.rationale,
                json.dumps(result.missing_fields, ensure_ascii=False),
                created_at,
            ),
        )
        self.connection.execute(
            """
            UPDATE raw_messages SET
                status = 'proposed', parser_version = ?, model_id = ?, confidence = ?,
                processed_at = ?, error_message = NULL
            WHERE id = ? AND status IN ('pending', 'failed')
            """,
            (
                result.parser_version,
                result.model_id,
                f"{result.confidence:.6f}",
                created_at,
                message.id,
            ),
        )
        proposal = TransactionProposal(
            proposal_id,
            message.id,
            attempt,
            result.kind,
            result.payload,
            result.confidence,
            result.requires_confirmation,
            "proposed",
            result.parser_id,
            result.parser_version,
            result.model_id,
            result.rationale,
            result.missing_fields,
            None,
            created_at,
            None,
            None,
            None,
        )
        LedgerRepository(self.connection).append_audit(
            action="propose",
            entity_type="transaction_proposal",
            entity_id=proposal_id,
            actor=actor,
            source=source,
            after=_proposal_snapshot(proposal),
        )
        return proposal

    def mark_parse_failed(
        self,
        *,
        message: RawMessage,
        error: str,
        parser_id: str,
        parser_version: str,
        model_id: str | None,
        actor: str,
        source: str,
    ) -> None:
        processed_at = utc_now()
        self.connection.execute(
            """
            UPDATE raw_messages SET
                status = 'failed', parser_version = ?, model_id = ?, processed_at = ?,
                error_message = ?
            WHERE id = ? AND status IN ('pending', 'failed')
            """,
            (parser_version, model_id, processed_at, error, message.id),
        )
        LedgerRepository(self.connection).append_audit(
            action="parse_failed",
            entity_type="raw_message",
            entity_id=message.id,
            actor=actor,
            source=source,
            reason=error,
            before={"status": message.status},
            after={"status": "failed", "parser_id": parser_id, "parser_version": parser_version},
        )

    def get_proposal(self, proposal_id: str) -> TransactionProposal:
        row = self.connection.execute(
            "SELECT * FROM transaction_proposals WHERE id = ?", (proposal_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"transaction proposal not found: {proposal_id}")
        return _proposal(row)

    def proposals_for_message(self, message_id: str) -> list[TransactionProposal]:
        rows = self.connection.execute(
            """
            SELECT * FROM transaction_proposals WHERE raw_message_id = ?
            ORDER BY attempt, created_at
            """,
            (message_id,),
        ).fetchall()
        return [_proposal(row) for row in rows]

    def confirm(
        self,
        *,
        proposal: TransactionProposal,
        transaction_id: str,
        reviewer: str,
        source: str,
    ) -> None:
        reviewed_at = utc_now()
        updated = self.connection.execute(
            """
            UPDATE transaction_proposals SET
                status = 'confirmed', transaction_id = ?, reviewed_at = ?, reviewer = ?
            WHERE id = ? AND status = 'proposed'
            """,
            (transaction_id, reviewed_at, reviewer, proposal.id),
        ).rowcount
        if updated != 1:
            raise ConflictError("proposal is no longer awaiting confirmation")
        self.connection.execute(
            """
            UPDATE raw_messages SET status = 'confirmed', processed_at = ?, error_message = NULL
            WHERE id = ?
            """,
            (reviewed_at, proposal.raw_message_id),
        )
        LedgerRepository(self.connection).append_audit(
            action="confirm",
            entity_type="transaction_proposal",
            entity_id=proposal.id,
            actor=reviewer,
            source=source,
            before={"status": "proposed"},
            after={"status": "confirmed", "transaction_id": transaction_id},
        )

    def reject(
        self,
        *,
        proposal: TransactionProposal,
        reason: str,
        reviewer: str,
        source: str,
    ) -> None:
        reviewed_at = utc_now()
        updated = self.connection.execute(
            """
            UPDATE transaction_proposals SET
                status = 'rejected', reviewed_at = ?, reviewer = ?, rejection_reason = ?
            WHERE id = ? AND status = 'proposed'
            """,
            (reviewed_at, reviewer, reason, proposal.id),
        ).rowcount
        if updated != 1:
            raise ConflictError("proposal is no longer awaiting review")
        self.connection.execute(
            "UPDATE raw_messages SET status = 'rejected', processed_at = ? WHERE id = ?",
            (reviewed_at, proposal.raw_message_id),
        )
        LedgerRepository(self.connection).append_audit(
            action="reject",
            entity_type="transaction_proposal",
            entity_id=proposal.id,
            actor=reviewer,
            source=source,
            reason=reason,
            before={"status": "proposed"},
            after={"status": "rejected"},
        )


def _raw_message(row: sqlite3.Row) -> RawMessage:
    return RawMessage(
        id=row["id"],
        channel=row["channel"],
        external_id=row["external_id"],
        received_at=row["received_at"],
        content=row["content"],
        status=row["status"],
        parser_version=row["parser_version"],
        model_id=row["model_id"],
        confidence=row["confidence"],
        processed_at=row["processed_at"],
        error_message=row["error_message"],
    )


def _proposal(row: sqlite3.Row) -> TransactionProposal:
    return TransactionProposal(
        id=row["id"],
        raw_message_id=row["raw_message_id"],
        attempt=int(row["attempt"]),
        kind=row["kind"],
        payload=json.loads(row["payload_json"]),
        confidence=int(row["confidence_ppm"]) / 1_000_000,
        requires_confirmation=bool(row["requires_confirmation"]),
        status=row["status"],
        parser_id=row["parser_id"],
        parser_version=row["parser_version"],
        model_id=row["model_id"],
        rationale=row["rationale"],
        missing_fields=tuple(json.loads(row["missing_fields_json"])),
        transaction_id=row["transaction_id"],
        created_at=row["created_at"],
        reviewed_at=row["reviewed_at"],
        reviewer=row["reviewer"],
        rejection_reason=row["rejection_reason"],
    )


def _proposal_snapshot(proposal: TransactionProposal) -> dict[str, Any]:
    return {
        "id": proposal.id,
        "raw_message_id": proposal.raw_message_id,
        "attempt": proposal.attempt,
        "kind": proposal.kind,
        "payload": proposal.payload,
        "confidence": proposal.confidence,
        "requires_confirmation": proposal.requires_confirmation,
        "status": proposal.status,
        "parser_id": proposal.parser_id,
        "parser_version": proposal.parser_version,
        "model_id": proposal.model_id,
        "missing_fields": proposal.missing_fields,
    }
