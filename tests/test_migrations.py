from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from moneyos import db


class MigrationTests(unittest.TestCase):
    def test_existing_v1_database_migrates_without_data_loss(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "v1.db"
            connection = sqlite3.connect(database)
            try:
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute(
                    """
                    CREATE TABLE schema_migrations (
                        version INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        applied_at TEXT NOT NULL
                    )
                    """
                )
                connection.executescript(db.MIGRATIONS[0].sql)
                connection.execute(
                    "INSERT INTO schema_migrations VALUES (1, 'initial_ledger', 'before-v2')"
                )
                connection.execute(
                    """
                    INSERT INTO raw_messages(
                        id, channel, external_id, received_at, content, status
                    ) VALUES ('old-message', 'cli', 'old-1', '2026-09-06', '麦当劳26', 'pending')
                    """
                )
                connection.commit()
            finally:
                connection.close()

            self.assertEqual(db.initialize(database), 2)
            migrated = db.connect(database)
            try:
                row = migrated.execute(
                    "SELECT content, status, processed_at FROM raw_messages WHERE id = 'old-message'"
                ).fetchone()
                self.assertEqual(row["content"], "麦当劳26")
                self.assertEqual(row["status"], "pending")
                self.assertIsNone(row["processed_at"])
                self.assertEqual(db.current_schema_version(migrated), 2)
            finally:
                migrated.close()


if __name__ == "__main__":
    unittest.main()
