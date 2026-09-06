from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from moneyos import db
from moneyos.cli import main
from moneyos.errors import ConflictError
from moneyos.export import export_database
from moneyos.inbox import InboxService
from moneyos.service import LedgerService


class BackupExportCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.database = self.root / "ledger.db"
        self.service = LedgerService(self.database)
        self.service.initialize()
        self.service.create_account("Wallet", opening_minor=10_000)
        self.service.create_category("Dining")
        self.transaction_id = self.service.record_expense(
            account="Wallet", category="Dining", amount_minor=2_600
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_backup_restore_and_integrity(self):
        backup = self.root / "backup.db"
        restored = self.root / "restored.db"
        db.backup_database(self.database, backup)
        db.restore_database(backup, restored)
        db.check_integrity(restored)
        restored_service = LedgerService(restored)
        self.assertEqual(len(restored_service.transactions()), len(self.service.transactions()))
        self.assertEqual(
            [item.balance_minor for item in restored_service.balances(role="user")],
            [item.balance_minor for item in self.service.balances(role="user")],
        )
        with self.assertRaises(ConflictError):
            db.backup_database(self.database, backup)
        with self.assertRaises(ConflictError):
            db.restore_database(backup, restored)

    def test_json_and_csv_export(self):
        json_path = self.root / "ledger.json"
        csv_path = self.root / "ledger.csv"
        export_database(self.database, json_path, format="json")
        export_database(self.database, csv_path, format="csv")

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["format"], "moneyos-ledger-export-v1")
        self.assertEqual(payload["schema_version"], 2)
        self.assertIn(self.transaction_id, {item["id"] for item in payload["transactions"]})
        self.assertTrue(payload["audit_log"])

        with csv_path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        transaction_rows = [row for row in rows if row["transaction_id"] == self.transaction_id]
        self.assertEqual(len(transaction_rows), 2)
        self.assertEqual(sum(int(row["posting_amount_minor"]) for row in transaction_rows), 0)

    def test_cli_end_to_end_and_expected_error_code(self):
        database = self.root / "cli.db"
        calls = (
            ["--db", str(database), "init"],
            ["--db", str(database), "account", "add", "Cash", "--opening", "100"],
            ["--db", str(database), "category", "add", "Food"],
            [
                "--db", str(database), "expense", "--account", "Cash",
                "--category", "Food", "--amount", "12.34", "--raw", "午饭12.34",
            ],
            ["--db", str(database), "doctor", "--json"],
        )
        output = io.StringIO()
        with redirect_stdout(output):
            for arguments in calls:
                self.assertEqual(main(arguments), 0)
        self.assertIn('"integrity": "ok"', output.getvalue())
        self.assertEqual(LedgerService(database).balances(role="user")[0].balance_minor, 8_766)

        error = io.StringIO()
        with redirect_stderr(error):
            code = main([
                "--db", str(database), "expense", "--account", "Missing",
                "--category", "Food", "--amount", "1",
            ])
        self.assertEqual(code, 2)
        self.assertIn("not found", error.getvalue())

    def test_cli_all_read_and_write_routes(self):
        database = self.root / "routes.db"
        output = io.StringIO()

        def run(*arguments: str) -> str:
            output.seek(0)
            output.truncate(0)
            with redirect_stdout(output):
                self.assertEqual(main(["--db", str(database), *arguments]), 0)
            return output.getvalue()

        run("init")
        run("account", "add", "Bank", "--opening", "1000")
        run("account", "add", "Cash")
        run("category", "add", "Food")
        run("category", "add", "Salary", "--kind", "income")
        self.assertIn("Bank", run("account", "list"))
        self.assertIn("CNY 1000.00", run("account", "balances"))
        self.assertIn("Food", run("category", "list"))

        run("income", "--account", "Bank", "--category", "Salary", "--amount", "50")
        run("transfer", "--from", "Bank", "--to", "Cash", "--amount", "100")
        run(
            "expense", "--account", "Bank", "--category", "Food", "--amount", "23.80",
            "--personal-amount", "13.80", "--owed-by", "Xiao Li",
        )
        service = LedgerService(database)
        expense_id = next(
            item.id for item in service.transactions() if item.kind == "expense"
        )
        run(
            "reimburse", "--account", "Bank", "--party", "Xiao Li", "--amount", "10",
            "--of", expense_id,
        )
        ordinary_id = service.record_expense(
            account="Bank", category="Food", amount_minor=2600
        )
        run(
            "refund", "--account", "Bank", "--category", "Food", "--amount", "10",
            "--of", ordinary_id,
        )
        self.assertIn("expense", run("transaction", "list", "--kind", "expense"))
        self.assertIn(ordinary_id, run("transaction", "show", ordinary_id))
        reversible_id = service.record_expense(
            account="Bank", category="Food", amount_minor=100
        )
        self.assertIn("Reversal posted", run(
            "transaction", "reverse", reversible_id, "--reason", "duplicate"
        ))
        self.assertIn("transaction", run("audit", "--limit", "10"))
        self.assertIn("Integrity: OK", run("doctor"))
        self.assertIn("Food", run("category", "balances"))

        backup_path = self.root / "routes-backup.db"
        restored_path = self.root / "routes-restored.db"
        json_path = self.root / "routes.json"
        csv_path = self.root / "routes.csv"
        self.assertIn("backup created", run("backup", str(backup_path)))
        self.assertIn("restored", run("restore", str(backup_path), "--target", str(restored_path)))
        self.assertIn("JSON", run("export", "--format", "json", "--output", str(json_path)))
        self.assertIn("CSV", run("export", "--format", "csv", "--output", str(csv_path)))

    def test_export_validation_and_conflict(self):
        output = self.root / "ledger.json"
        with self.assertRaisesRegex(Exception, "format"):
            export_database(self.database, output, format="xml")
        output.write_text("occupied", encoding="utf-8")
        with self.assertRaises(ConflictError):
            export_database(self.database, output, format="json")

    def test_cli_inbox_routes(self):
        database = self.root / "inbox-cli.db"
        service = LedgerService(database)
        service.initialize()
        service.create_account("WeChat", opening_minor=10_000)
        service.create_category("Dining")
        output = io.StringIO()
        error = io.StringIO()

        def run(*arguments: str) -> str:
            output.seek(0)
            output.truncate(0)
            with redirect_stdout(output), redirect_stderr(error):
                self.assertEqual(main(["--db", str(database), *arguments]), 0)
            return output.getvalue()

        self.assertIn(
            "Ingested", run("inbox", "add", "麦当劳26", "--external-id", "cli-1")
        )
        self.assertIn(
            "Already ingested",
            run("inbox", "add", "麦当劳26", "--external-id", "cli-1"),
        )
        inbox = InboxService(database)
        message = inbox.messages()[0]
        self.assertIn("pending", run("inbox", "list", "--status", "pending"))
        self.assertIn("Proposal", run("inbox", "parse", message.id))
        proposal = inbox.proposals_for_message(message.id)[0]
        self.assertIn(message.id, run("inbox", "show", message.id))
        self.assertIn(
            "transaction posted",
            run(
                "inbox", "confirm", proposal.id,
                "--account", "WeChat", "--category", "Dining",
            ),
        )
        self.assertIn("confirmed", run("inbox", "list", "--status", "confirmed"))

        run("inbox", "add", "午饭10", "--external-id", "cli-2")
        self.assertIn("Parsed 1 message", run("inbox", "parse"))
        second = next(item for item in inbox.messages() if item.external_id == "cli-2")
        second_proposal = inbox.proposals_for_message(second.id)[0]
        self.assertIn(
            "Proposal rejected",
            run("inbox", "reject", second_proposal.id, "--reason", "not real"),
        )

        run("inbox", "add", "没有金额", "--external-id", "cli-3")
        self.assertIn("1 failed", run("inbox", "parse"))
        self.assertIn("Failed", error.getvalue())


if __name__ == "__main__":
    unittest.main()
