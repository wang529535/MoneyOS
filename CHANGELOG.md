# Changelog

All notable project changes will be documented here.

## 0.2.0.dev0 — 2026-09-06

### Added

- Versioned V1-to-V2 database migration preserving existing ledger data.
- Append-only raw inbox with `(channel, external_id)` idempotency.
- Replaceable transaction-parser protocol and deterministic Chinese baseline parser.
- Structured transaction proposals with confidence, missing fields, rationale, and complete
  parser/model provenance.
- Explicit confirmation and rejection workflows.
- Batch parsing that records failures without blocking other messages.
- Expense, income, transfer, and settled shared-payment proposal execution.
- Crash-recoverable confirmation based on unique raw-message transaction linkage.
- Inbox integrity diagnostics, immutable proposal payloads, and immutable raw content.
- Inbox CLI commands and comprehensive parser, migration, service, and end-to-end tests.

### Changed

- JSON exports now include raw messages and transaction proposals.
- `doctor` now validates ledger and inbox consistency.

## 0.1.0.dev0 — 2026-09-06

### Added

- V0.1 balanced SQLite ledger foundation.
- Accounts, categories, expenses, income, transfers, refunds, reimbursements, and reversals.
- Exact integer minor-unit arithmetic.
- Append-only audit records and raw-input preservation.
- Database migrations and integrity triggers.
- CLI, validated backup/restore, JSON/CSV export, and doctor command.
- Standard-library automated test suite.
- Data model, architecture, roadmap, security, and architecture-decision documentation.
