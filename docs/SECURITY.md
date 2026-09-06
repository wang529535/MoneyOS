# Security and Data-Safety Model

Last updated: 2026-09-06

## Current guarantees

V0.1 makes the following guarantees when financial writes go through `LedgerService` or the
CLI:

- SQL values are parameterized;
- a transaction and its postings commit atomically;
- a posted transaction must contain at least two postings and balance to zero;
- posted postings and transaction facts cannot be updated or deleted;
- corrections append reversal transactions;
- transaction links become immutable when posted;
- audit rows cannot be updated or deleted;
- foreign-key checks are enabled on every application connection;
- backup and restore run SQLite integrity and foreign-key checks;
- restore never overwrites an existing target;
- no command exposes arbitrary SQL, Python, shell, or model execution.
- raw-message content and identity are immutable after ingestion;
- proposal payload and parser provenance are immutable after creation;
- confirmed/rejected inbox records are terminal;
- every included parser result requires an explicit confirmation before posting;
- a unique raw-message link prevents duplicate primary ledger transactions during retries.

These controls establish the boundary future AI tools must use. An AI parser may propose an
operation, but it receives no special authority to bypass domain validation.

## Limitations

V0.1 is a local, single-user application. It does not provide:

- database encryption at rest;
- OS-user isolation or application authentication;
- encrypted synchronization;
- malicious-host protection;
- signed audit records resistant to a user editing the SQLite file with external tools;
- attachment malware scanning;
- a prompt-injection defense layer, because no model or external content executes yet.

Anyone with write access to the database file and a general SQLite tool can alter the file by
disabling or bypassing application controls. File permissions, full-disk encryption, device
security, and off-device backup protection remain deployment responsibilities.

## Safe operating guidance

- Keep the ledger on a trusted device with full-disk encryption.
- Do not place unencrypted backups in a public sync folder.
- Run `moneyos doctor` after moving or restoring a database.
- Keep multiple dated backups and periodically test a restore to a new path.
- Reconcile important account balances against independent statements.
- Never expose a database file directly to an untrusted model or plugin.

## Future AI boundary

Model-powered components must follow least privilege:

```text
natural-language input
        -> structured proposal
        -> schema validation
        -> user confirmation when needed
        -> LedgerService
        -> audit log + ledger
```

Analytics should use a separate read-only connection or sandbox. Generated SQL must never be
treated as authorization for a ledger write.

## Reporting vulnerabilities

Until a public repository and private security channel exist, do not publish exploitable
financial-data issues in public discussions. When the repository is created, add a supported
versions table, contact method, disclosure timeline, and GitHub private vulnerability
reporting instructions before inviting external users.
