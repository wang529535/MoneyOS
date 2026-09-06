from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from moneyos import db
from moneyos.errors import ConflictError, ValidationError
from moneyos.service import LedgerService


class LedgerTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.database = self.root / "ledger.db"
        self.service = LedgerService(self.database)
        self.service.initialize()

    def tearDown(self):
        self.temporary.cleanup()

    def seed(self):
        self.service.create_account("WeChat", opening_minor=100_000)
        self.service.create_account("Cash", opening_minor=10_000)
        self.service.create_category("Dining", kind="expense")
        self.service.create_category("Salary", kind="income")

    def balance(self, name: str, role: str | None = None) -> int:
        balances = self.service.balances(role=role)
        return next(item.balance_minor for item in balances if item.account.name == name)

    def test_initialize_is_idempotent(self):
        self.assertEqual(self.service.initialize(), 1)
        self.assertEqual(self.service.initialize(), 1)
        connection = db.connect(self.database)
        try:
            self.assertEqual(db.current_schema_version(connection), 1)
        finally:
            connection.close()

    def test_opening_balances_follow_normal_sign(self):
        self.service.create_account("Bank", kind="asset", opening_minor=50_000)
        self.service.create_account("Credit Card", kind="liability", opening_minor=20_000)
        self.assertEqual(self.balance("Bank", "user"), 50_000)
        self.assertEqual(self.balance("Credit Card", "user"), 20_000)
        self.assertEqual(self._unbalanced_count(), 0)

    def test_expense_and_income_are_exact(self):
        self.seed()
        expense_id = self.service.record_expense(
            account="WeChat",
            category="Dining",
            amount_minor=1,
            raw_input="测试最小金额 0.01",
        )
        income_id = self.service.record_income(
            account="WeChat", category="Salary", amount_minor=50_000
        )
        self.assertEqual(self.balance("WeChat", "user"), 149_999)
        self.assertEqual(self.balance("Dining", "category"), 1)
        self.assertEqual(self.balance("Salary", "category"), 50_000)
        self.assertEqual(self.service.transaction(expense_id).raw_input, "测试最小金额 0.01")
        self.assertEqual(self.service.transaction(income_id).kind, "income")
        self.assertEqual(self._unbalanced_count(), 0)

    def test_transfer_never_touches_categories(self):
        self.seed()
        before = {item.account.name: item.balance_minor for item in self.service.balances(role="category")}
        self.service.record_transfer(from_account="WeChat", to_account="Cash", amount_minor=2_600)
        after = {item.account.name: item.balance_minor for item in self.service.balances(role="category")}
        self.assertEqual(before, after)
        self.assertEqual(self.balance("WeChat", "user"), 97_400)
        self.assertEqual(self.balance("Cash", "user"), 12_600)

    def test_shared_expense_separates_payment_cost_and_receivable(self):
        self.seed()
        expense_id = self.service.record_expense(
            account="WeChat",
            category="Dining",
            amount_minor=23_800,
            personal_minor=13_800,
            owed_by="小李",
            description="海底捞",
        )
        self.assertEqual(self.balance("WeChat"), 76_200)
        self.assertEqual(self.balance("Dining"), 13_800)
        self.assertEqual(self.balance("Receivable:小李"), 10_000)
        transaction = self.service.transaction(expense_id)
        self.assertEqual(transaction.metadata["personal_amount_minor"], 13_800)
        self.assertEqual(sum(posting.amount_minor for posting in transaction.postings), 0)

        reimbursement_id = self.service.record_reimbursement(
            account="WeChat",
            party="小李",
            amount_minor=10_000,
            original_transaction_id=expense_id,
        )
        self.assertEqual(self.balance("WeChat"), 86_200)
        self.assertEqual(self.balance("Dining"), 13_800)
        self.assertEqual(self.balance("Receivable:小李"), 0)
        reimbursement = self.service.transaction(reimbursement_id)
        self.assertEqual(reimbursement.related[0]["relation"], "reimbursement_of")

        with self.assertRaises(ValidationError):
            self.service.record_reimbursement(
                account="WeChat",
                party="小李",
                amount_minor=1,
                original_transaction_id=expense_id,
            )

    def test_refund_reduces_expense_and_cannot_exceed_original(self):
        self.seed()
        expense_id = self.service.record_expense(
            account="WeChat", category="Dining", amount_minor=2_600
        )
        refund_id = self.service.record_refund(
            account="WeChat",
            category="Dining",
            amount_minor=1_000,
            original_transaction_id=expense_id,
        )
        self.assertEqual(self.balance("Dining"), 1_600)
        with self.assertRaises(ValidationError):
            self.service.record_refund(
                account="WeChat",
                category="Dining",
                amount_minor=1_601,
                original_transaction_id=expense_id,
            )

        self.service.reverse_transaction(refund_id, reason="refund entered by mistake")
        self.assertEqual(self.balance("Dining"), 2_600)
        replacement = self.service.record_refund(
            account="WeChat",
            category="Dining",
            amount_minor=2_600,
            original_transaction_id=expense_id,
        )
        self.assertEqual(self.service.transaction(replacement).kind, "refund")
        self.assertEqual(self.balance("Dining"), 0)

    def test_reversal_is_append_only_and_exact(self):
        self.seed()
        expense_id = self.service.record_expense(
            account="WeChat", category="Dining", amount_minor=2_600
        )
        reversal_id = self.service.reverse_transaction(expense_id, reason="duplicate")
        self.assertEqual(self.balance("WeChat"), 100_000)
        self.assertEqual(self.balance("Dining"), 0)
        self.assertEqual(self.service.transaction(expense_id).reversed_by_id, reversal_id)
        self.assertEqual(self.service.transaction(reversal_id).kind, "reversal")
        with self.assertRaises(ConflictError):
            self.service.reverse_transaction(expense_id, reason="again")
        with self.assertRaises(ValidationError):
            self.service.reverse_transaction(reversal_id, reason="reinstate")

    def test_original_with_active_dependent_must_not_be_reversed(self):
        self.seed()
        expense_id = self.service.record_expense(
            account="WeChat", category="Dining", amount_minor=2_600
        )
        self.service.record_refund(
            account="WeChat",
            category="Dining",
            amount_minor=1_000,
            original_transaction_id=expense_id,
        )
        with self.assertRaises(ConflictError):
            self.service.reverse_transaction(expense_id, reason="cannot orphan refund")

    def test_database_guards_balance_and_immutability(self):
        self.seed()
        expense_id = self.service.record_expense(
            account="WeChat", category="Dining", amount_minor=100
        )
        connection = db.connect(self.database)
        try:
            posting_id = connection.execute(
                "SELECT id FROM postings WHERE transaction_id = ? LIMIT 1", (expense_id,)
            ).fetchone()[0]
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE postings SET amount_minor = 5 WHERE id = ?", (posting_id,))
            audit_id = connection.execute("SELECT id FROM audit_log LIMIT 1").fetchone()[0]
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM audit_log WHERE id = ?", (audit_id,))

            connection.execute(
                """
                INSERT INTO transactions(
                    id, kind, amount_minor, currency, occurred_on, description,
                    actor, source, created_at
                ) VALUES ('bad', 'expense', 100, 'CNY', '2026-09-06', 'bad', 'test', 'test', 'now')
                """
            )
            account_id = connection.execute(
                "SELECT id FROM accounts WHERE name = 'WeChat'"
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO postings(transaction_id, account_id, amount_minor) VALUES ('bad', ?, -100)",
                (account_id,),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE transactions SET status = 'posted' WHERE id = 'bad'")
        finally:
            connection.close()

    def test_validation_rolls_back_auto_created_receivable(self):
        self.seed()
        before = len(self.service.accounts())
        with self.assertRaises(ValidationError):
            self.service.record_expense(
                account="WeChat",
                category="Dining",
                amount_minor=100,
                personal_minor=101,
                owed_by="Nobody",
            )
        self.assertEqual(len(self.service.accounts()), before)

    def test_domain_validation_and_conflicts(self):
        self.service.create_account("Wallet")
        with self.assertRaises(ConflictError):
            self.service.create_account("wallet")
        with self.assertRaises(ValidationError):
            self.service.create_account("Bad", kind="expense")
        with self.assertRaises(ValidationError):
            self.service.create_account("Bad Opening", opening_minor=-1)
        with self.assertRaises(ValidationError):
            self.service.create_category("Bad Category", kind="asset")
        with self.assertRaises(ValidationError):
            self.service.create_category("USD Food", currency="USDT")
        with self.assertRaises(ValidationError):
            self.service.transactions(limit=0)
        with self.assertRaises(ValidationError):
            self.service.transactions(kind="unknown")
        with self.assertRaises(ValidationError):
            self.service.audit(limit=1001)

    def test_currency_role_and_date_validation(self):
        self.service.create_account("CNY Wallet", currency="CNY")
        self.service.create_account("USD Wallet", currency="USD")
        self.service.create_category("CNY Food", currency="CNY")
        self.service.create_category("USD Food", currency="USD")
        self.service.create_category("CNY Salary", kind="income", currency="CNY")
        with self.assertRaises(ValidationError):
            self.service.record_expense(
                account="CNY Wallet", category="USD Food", amount_minor=100
            )
        with self.assertRaises(ValidationError):
            self.service.record_transfer(
                from_account="CNY Wallet", to_account="USD Wallet", amount_minor=100
            )
        with self.assertRaises(ValidationError):
            self.service.record_transfer(
                from_account="CNY Wallet", to_account="CNY Wallet", amount_minor=100
            )
        with self.assertRaises(ValidationError):
            self.service.record_income(
                account="CNY Wallet",
                category="CNY Food",
                amount_minor=100,
            )
        with self.assertRaises(ValidationError):
            self.service.record_expense(
                account="CNY Wallet",
                category="CNY Food",
                amount_minor=100,
                occurred_on="09/06/2026",
            )
        with self.assertRaises(ValidationError):
            self.service.record_expense(
                account="CNY Wallet", category="CNY Salary", amount_minor=100
            )

    def test_shared_payment_validation_and_partial_reimbursement(self):
        self.seed()
        with self.assertRaises(ValidationError):
            self.service.record_expense(
                account="WeChat", category="Dining", amount_minor=100, personal_minor=50
            )
        with self.assertRaises(ValidationError):
            self.service.record_expense(
                account="WeChat",
                category="Dining",
                amount_minor=100,
                personal_minor=100,
                owed_by="X",
            )
        expense_id = self.service.record_expense(
            account="WeChat",
            category="Dining",
            amount_minor=100,
            personal_minor=40,
            owed_by="X",
        )
        first = self.service.record_reimbursement(
            account="WeChat", party="X", amount_minor=20, original_transaction_id=expense_id
        )
        self.service.reverse_transaction(first, reason="wrong settlement")
        self.service.record_reimbursement(
            account="WeChat", party="X", amount_minor=60, original_transaction_id=expense_id
        )
        self.assertEqual(self.balance("Receivable:X"), 0)
        with self.assertRaises(ValidationError):
            self.service.record_reimbursement(
                account="WeChat", party="Other", amount_minor=1,
                original_transaction_id=expense_id,
            )

    def test_raw_input_is_preserved_exactly_and_text_is_bounded(self):
        self.seed()
        raw = "  晚上和小李吃饭 26  \n"
        transaction_id = self.service.record_expense(
            account="WeChat", category="Dining", amount_minor=2600, raw_input=raw
        )
        self.assertEqual(self.service.transaction(transaction_id).raw_input, raw)
        with self.assertRaises(ValidationError):
            self.service.record_expense(
                account="WeChat",
                category="Dining",
                amount_minor=1,
                description="x" * 501,
            )
        with self.assertRaises(ValidationError):
            self.service.record_expense(
                account="WeChat",
                category="Dining",
                amount_minor=1,
                raw_input="x" * 100_001,
            )

    def test_transaction_links_and_reversal_marker_are_database_guarded(self):
        self.seed()
        expense_id = self.service.record_expense(
            account="WeChat", category="Dining", amount_minor=100
        )
        refund_id = self.service.record_refund(
            account="WeChat", category="Dining", amount_minor=50,
            original_transaction_id=expense_id,
        )
        connection = db.connect(self.database)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM transaction_links WHERE from_transaction_id = ?", (refund_id,)
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE transactions SET reversed_by_id = ? WHERE id = ?",
                    (refund_id, expense_id),
                )
        finally:
            connection.close()

    def _unbalanced_count(self) -> int:
        connection = db.connect(self.database)
        try:
            return int(connection.execute(
                """
                SELECT count(*) FROM (
                    SELECT t.id FROM transactions t
                    JOIN postings p ON p.transaction_id = t.id
                    WHERE t.status = 'posted'
                    GROUP BY t.id HAVING sum(p.amount_minor) != 0 OR count(*) < 2
                )
                """
            ).fetchone()[0])
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
