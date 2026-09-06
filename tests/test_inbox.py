from __future__ import annotations

import math
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from moneyos import db
from moneyos.errors import ConflictError, ValidationError
from moneyos.inbox import InboxService
from moneyos.parser import DeterministicParser, ParseError, ParseResult
from moneyos.service import LedgerService


class InboxTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.database = self.root / "ledger.db"
        self.ledger = LedgerService(self.database)
        self.ledger.initialize()
        self.ledger.create_account("WeChat", opening_minor=100_000)
        self.ledger.create_account("Bank", opening_minor=50_000)
        self.ledger.create_category("Dining")
        self.ledger.create_category("Salary", kind="income")
        self.inbox = InboxService(self.database)

    def tearDown(self):
        self.temporary.cleanup()

    def balance(self, name: str) -> int:
        return next(
            item.balance_minor for item in self.ledger.balances()
            if item.account.name == name
        )

    def test_ingestion_is_idempotent_by_channel_external_id(self):
        first, created = self.inbox.ingest(
            "  麦当劳26\n", channel="feishu", external_id="message-1"
        )
        second, created_again = self.inbox.ingest(
            "  麦当劳26\n", channel="feishu", external_id="message-1"
        )
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first, second)
        self.assertEqual(first.content, "  麦当劳26\n")
        with self.assertRaises(ConflictError):
            self.inbox.ingest(
                "different", channel="feishu", external_id="message-1"
            )

    def test_simple_expense_proposal_confirmation_is_idempotent(self):
        message, _ = self.inbox.ingest("麦当劳26", external_id="simple-expense")
        proposal = self.inbox.parse_message(message.id)
        self.assertEqual(proposal.kind, "expense")
        self.assertEqual(proposal.missing_fields, ("account", "category"))
        with self.assertRaises(ValidationError):
            self.inbox.confirm(proposal.id)
        self.assertEqual(self.inbox.proposal(proposal.id).status, "proposed")

        transaction_id = self.inbox.confirm(
            proposal.id, account="WeChat", category="Dining"
        )
        again = self.inbox.confirm(
            proposal.id, account="WeChat", category="Dining"
        )
        self.assertEqual(again, transaction_id)
        transaction = self.ledger.transaction(transaction_id)
        self.assertEqual(transaction.raw_message_id, message.id)
        self.assertEqual(transaction.raw_input, "麦当劳26")
        self.assertEqual(self.balance("WeChat"), 97_400)
        self.assertEqual(self.balance("Dining"), 2_600)
        self.assertEqual(self.inbox.message(message.id).status, "confirmed")
        self.assertEqual(self.inbox.proposal(proposal.id).status, "confirmed")
        self.assertEqual(
            len([item for item in self.ledger.transactions() if item.kind == "expense"]), 1
        )

    def test_income_and_transfer_confirmation(self):
        income_message, _ = self.inbox.ingest("妈妈给了500")
        income_proposal = self.inbox.parse_message(income_message.id)
        income_id = self.inbox.confirm(
            income_proposal.id, account="WeChat", category="Salary"
        )
        self.assertEqual(self.ledger.transaction(income_id).kind, "income")
        self.assertEqual(self.balance("WeChat"), 150_000)

        transfer_message, _ = self.inbox.ingest("从WeChat转100到Bank")
        transfer_proposal = self.inbox.parse_message(transfer_message.id)
        transfer_id = self.inbox.confirm(transfer_proposal.id)
        self.assertEqual(self.ledger.transaction(transfer_id).kind, "transfer")
        self.assertEqual(self.balance("WeChat"), 140_000)
        self.assertEqual(self.balance("Bank"), 60_000)

    def test_shared_message_posts_expense_and_settlement_once(self):
        message, _ = self.inbox.ingest(
            "和小李吃海底捞我先付238，他后来转我100", external_id="shared-1"
        )
        proposal = self.inbox.parse_message(message.id)
        expense_id = self.inbox.confirm(
            proposal.id, account="WeChat", category="Dining"
        )
        self.assertEqual(self.balance("WeChat"), 86_200)
        self.assertEqual(self.balance("Dining"), 13_800)
        self.assertEqual(self.balance("Receivable:小李"), 0)
        kinds = [item.kind for item in self.ledger.transactions()]
        self.assertEqual(kinds.count("expense"), 1)
        self.assertEqual(kinds.count("reimbursement"), 1)
        self.assertEqual(self.inbox.confirm(
            proposal.id, account="WeChat", category="Dining"
        ), expense_id)
        kinds_after = [item.kind for item in self.ledger.transactions()]
        self.assertEqual(kinds_after.count("expense"), 1)
        self.assertEqual(kinds_after.count("reimbursement"), 1)

    def test_batch_parse_records_failures_and_allows_retry(self):
        good, _ = self.inbox.ingest("地铁2", external_id="batch-good")
        bad, _ = self.inbox.ingest("今天没有写金额", external_id="batch-bad")
        result = self.inbox.parse_pending()
        self.assertEqual([item.raw_message_id for item in result.proposals], [good.id])
        self.assertEqual(result.failures[0][0], bad.id)
        failed = self.inbox.message(bad.id)
        self.assertEqual(failed.status, "failed")
        self.assertIn("no monetary amount", failed.error_message or "")
        with self.assertRaises(ParseError):
            self.inbox.parse_message(bad.id)
        retried_batch = self.inbox.parse_pending()
        self.assertEqual(retried_batch.proposals, ())
        self.assertEqual(retried_batch.failures, ())
        audit_actions = [item["action"] for item in self.ledger.audit()]
        self.assertIn("parse_failed", audit_actions)
        self.assertIn("propose", audit_actions)

    def test_reject_is_terminal_and_audited(self):
        message, _ = self.inbox.ingest("不确定消费88")
        proposal = self.inbox.parse_message(message.id)
        self.inbox.reject(proposal.id, reason="not a real transaction")
        self.inbox.reject(proposal.id, reason="idempotent retry")
        self.assertEqual(self.inbox.message(message.id).status, "rejected")
        rejected = self.inbox.proposal(proposal.id)
        self.assertEqual(rejected.status, "rejected")
        self.assertEqual(rejected.rejection_reason, "not a real transaction")
        with self.assertRaises(ConflictError):
            self.inbox.confirm(proposal.id, account="WeChat", category="Dining")

    def test_raw_messages_and_proposals_are_not_deletable(self):
        message, _ = self.inbox.ingest("午饭10")
        proposal = self.inbox.parse_message(message.id)
        connection = db.connect(self.database)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM transaction_proposals WHERE id = ?", (proposal.id,)
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM raw_messages WHERE id = ?", (message.id,))
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE raw_messages SET content = 'changed' WHERE id = ?", (message.id,)
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE transaction_proposals SET payload_json = '{}' WHERE id = ?",
                    (proposal.id,),
                )
        finally:
            connection.close()

    def test_input_and_query_validation(self):
        with self.assertRaises(ValidationError):
            self.inbox.ingest(" ")
        with self.assertRaises(ValidationError):
            self.inbox.ingest("x", channel=" ")
        with self.assertRaises(ValidationError):
            self.inbox.messages(status="unknown")
        with self.assertRaises(ValidationError):
            self.inbox.messages(limit=0)
        with self.assertRaises(ValidationError):
            self.inbox.reject("missing", reason=" ")

    def test_bad_parser_result_fails_closed(self):
        class BadParser(DeterministicParser):
            parser_id = "test.bad"

            def parse(self, content: str, *, context=None) -> ParseResult:
                valid = super().parse(content, context=context)
                return replace(valid, confidence=2.0)

        message, _ = self.inbox.ingest("午饭10")
        inbox = InboxService(self.database, parser=BadParser())
        with self.assertRaises(ParseError):
            inbox.parse_message(message.id)
        failed = inbox.message(message.id)
        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.parser_version, BadParser.parser_version)

    def test_non_finite_or_inconsistent_parser_output_fails_closed(self):
        class NonFiniteParser(DeterministicParser):
            def parse(self, content: str, *, context=None) -> ParseResult:
                return replace(super().parse(content, context=context), confidence=math.nan)

        message, _ = self.inbox.ingest("午饭10")
        with self.assertRaises(ParseError):
            InboxService(self.database, parser=NonFiniteParser()).parse_message(message.id)

        class BadSplitParser(DeterministicParser):
            def parse(self, content: str, *, context=None) -> ParseResult:
                result = super().parse(content, context=context)
                return replace(
                    result,
                    payload={**result.payload, "personal_minor": 900, "settled_minor": 200},
                )

        second, _ = self.inbox.ingest("晚饭10")
        with self.assertRaises(ParseError):
            InboxService(self.database, parser=BadSplitParser()).parse_message(second.id)

    def test_confirmation_recovers_an_already_posted_raw_message(self):
        message, _ = self.inbox.ingest("午饭10", external_id="recovery-1")
        proposal = self.inbox.parse_message(message.id)
        existing_id = self.ledger.record_expense(
            account="WeChat",
            category="Dining",
            amount_minor=1000,
            raw_input=message.content,
            raw_message_id=message.id,
            source="inbox:cli",
        )
        recovered_id = self.inbox.confirm(
            proposal.id, account="WeChat", category="Dining"
        )
        self.assertEqual(recovered_id, existing_id)
        self.assertEqual(self.inbox.proposal(proposal.id).status, "confirmed")
        self.assertEqual(
            len([item for item in self.ledger.transactions() if item.kind == "expense"]), 1
        )

    def test_parser_receives_minimal_ledger_vocabulary(self):
        observed = {}

        class ContextParser(DeterministicParser):
            def parse(self, content: str, *, context=None) -> ParseResult:
                observed["context"] = context
                return super().parse(content, context=context)

        message, _ = self.inbox.ingest("午饭10")
        InboxService(self.database, parser=ContextParser()).parse_message(message.id)
        context = observed["context"]
        self.assertEqual(context.default_currency, "CNY")
        self.assertEqual(set(context.accounts), {"Bank", "WeChat"})
        self.assertIn("Dining", context.expense_categories)
        self.assertIn("Salary", context.income_categories)

    def test_recovery_refuses_a_mismatched_linked_transaction(self):
        message, _ = self.inbox.ingest("午饭10", external_id="bad-recovery")
        proposal = self.inbox.parse_message(message.id)
        self.ledger.record_income(
            account="WeChat",
            category="Salary",
            amount_minor=1000,
            raw_input=message.content,
            raw_message_id=message.id,
            source="test",
        )
        with self.assertRaises(ConflictError):
            self.inbox.confirm(proposal.id, account="WeChat", category="Dining")
        self.assertEqual(self.inbox.proposal(proposal.id).status, "proposed")


if __name__ == "__main__":
    unittest.main()
