# MoneyOS V0.1 Architecture

Status: updated for V0.2
Last updated: 2026-09-06

## 1. Objective

V0.1 is a local, reliable ledger that runs with no AI and no external service. It provides a
small CLI, a SQLite database, append-only financial history, audit records, backups, exports,
and tests.

The implementation should be useful on its own while leaving stable seams for later AI,
channel, analytics, and provider components.

## 2. Boundaries

```text
CLI / future Channel Adapters
              |
              v
       Raw Inbox Service
              |
      Transaction Parser --> structured proposal only
              |
       explicit review
              |
              v
     Ledger Application Service  <-- only financial write authority
              |
              v
       Ledger repository
              |
              v
 SQLite (inbox, proposals, postings, audit, migrations)
```

Rules:

- the CLI contains argument parsing and presentation, not accounting decisions;
- application services are the only supported write boundary;
- the repository owns SQL and row mapping;
- migrations own persistent schema changes;
- analytics read posted facts and never mutate ledger tables;
- future AI tools call application services instead of receiving direct SQL write access.

## 3. Package layout

```text
moneyos/
  __init__.py
  __main__.py
  cli.py          command parsing and terminal presentation
  db.py           connections, migrations, backup and restore
  errors.py       stable domain errors
  money.py        Decimal/minor-unit conversion
  repository.py   SQL persistence and read models
  service.py      accounting workflows and validation
  export.py       read-only CSV/JSON exports
  parser.py       replaceable parser protocol and deterministic baseline
  inbox.py        ingestion, parsing, review, and recovery orchestration
  inbox_repository.py  raw-message and proposal persistence
tests/
docs/
```

## 4. Dependency policy

The V0.1 runtime uses only Python's standard library:

- `sqlite3` for persistence;
- `argparse` for the CLI;
- `decimal` for input parsing;
- `uuid`, `json`, `csv`, and `datetime` for supporting concerns;
- `unittest` for the baseline test suite.

Why now:

- installation works without a package index or network access;
- Python 3.14 compatibility is not gated by third-party releases;
- the first version's queries are small enough for explicit SQL to remain clear;
- contributors can run the complete suite immediately.

This is not a ban on third-party libraries. Pydantic, SQLAlchemy, Typer, Polars, Plotly, and AI
SDKs can be introduced behind existing boundaries when their value exceeds their operational
cost. Persistent schema and domain behavior must not depend on a specific UI or model SDK.

## 5. Database lifecycle

Each command opens a connection configured with:

```text
foreign_keys = ON
journal_mode = WAL
busy_timeout = 5000 ms
```

Schema migrations are ordered, versioned, and applied transactionally. `moneyos init` is
idempotent. The current schema version is recorded in `schema_migrations`.

All ledger writes run in one `BEGIN IMMEDIATE` transaction so a transaction header, postings,
links, and audit record either commit together or do not appear at all.

## 6. Security model

V0.1 is a single-user local application, but it establishes the future agent boundary:

- no arbitrary SQL write command exists;
- posted postings cannot be edited or deleted;
- corrections append reversals;
- user inputs become SQL parameters, never string-built SQL;
- backup restore refuses to overwrite an existing target;
- export is read-only;
- audit rows are append-only;
- raw input is preserved when supplied.

SQLite file permissions and host security remain the user's responsibility. Encryption at rest
is not claimed in V0.1.

## 7. Failure behavior

Expected domain errors have stable, readable messages and a non-zero CLI exit code. A failed
posting transaction rolls back completely. SQLite integrity failures are translated where a
clear user action exists; unexpected failures retain their traceback in development/test
contexts rather than being silently treated as success.

## 8. Extension seams

### AI bookkeeping (V0.2 and later)

A parser produces a proposed command DTO. Schema and business validation still happen in the
application service. V0.2 requires explicit confirmation for every included parser result.
Future model-backed parsers implement the same protocol and record model provenance.

### Web and channels

Web, Feishu, Telegram, and future mobile adapters translate external messages into the same
application calls. They do not own ledger logic.

### Analytics

Read-only analytics uses documented views or a read-only SQLite connection. Dynamic SQL is
parsed/guarded in a later sandbox and never shares write authority with the ledger service.

### Model providers

Provider code belongs outside the ledger package. Local and cloud models can be replaced
without migrating financial facts.

## 9. V0.1 acceptance criteria

The implementation is acceptable when all of these are demonstrated automatically:

1. a new database initializes twice without damage;
2. CNY 0.01 remains exact through posting and export;
3. expenses and income change the correct account and category balances;
4. transfers do not change income or expense totals;
5. a shared payment separates cash paid, personal expense, and receivable;
6. reimbursement settles the receivable without creating income;
7. refunds reduce the linked category cost;
8. reversing a transaction exactly neutralizes its postings;
9. audit history is created and cannot be mutated;
10. backup/restore produces an equivalent, valid SQLite database;
11. the principal workflow can be completed through the CLI.

## 10. Explicit non-goals

V0.1 does not include an LLM, dashboard, bank synchronization, cloud account, vector database,
arbitrary plugin execution, investment portfolio, tax engine, multi-user permissions, or
native mobile application.
