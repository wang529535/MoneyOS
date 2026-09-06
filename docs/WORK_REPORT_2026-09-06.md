# MoneyOS Foundation Work Report — 2026-09-06

## Outcome

The directory started with one vision document and no valid Git repository or implementation.
It now contains a runnable, installable, tested V0.1 ledger foundation.

## Delivered

### Product and engineering decisions

- Defined the V0.1 scope and explicit non-goals.
- Selected balanced postings for the ledger core.
- Defined account kinds and roles.
- Specified exact integer minor-unit money arithmetic.
- Defined append-only reversal, audit, and transaction-link behavior.
- Documented module boundaries for future AI, channel, provider, and analytics layers.
- Recorded two architecture decisions and a staged implementation roadmap.

### Runtime implementation

- Versioned SQLite migration runner.
- WAL mode, foreign keys, busy timeout, integrity checks, and transactional writes.
- Accounts: asset and liability.
- Categories: expense and income.
- Transactions: opening, expense, income, transfer, refund, reimbursement, and reversal.
- Shared-payment representation with personal cost and party receivable.
- Partial reimbursement and refund limits.
- Immutable posted postings, financial transaction facts, and semantic links.
- Append-only audit log.
- Preserved raw input.
- User-facing balances with correct debit/credit normal signs.

### CLI

- `init`
- `account add/list/balances`
- `category add/list/balances`
- `expense`
- `income`
- `transfer`
- `refund`
- `reimburse`
- `transaction list/show/reverse`
- `audit`
- `backup`
- `restore`
- `export`
- `doctor`

### Data safety

- Posted transactions require at least two postings and a zero sum.
- Posting currencies must match the transaction currency.
- Corrections never delete the original transaction.
- Active child refunds/reimbursements must be reversed before their parent expense.
- Reversal markers must point to a valid posted reversal and matching immutable link.
- Backup/restore destinations cannot be overwritten accidentally.
- Restored databases pass SQLite and foreign-key integrity checks.

### Documentation

- Project README and quick start.
- Data model specification.
- Architecture and security model.
- Version roadmap.
- Contributor guide, changelog, MIT license, and ADRs.

## Verification evidence

The final implementation passed:

```text
pytest:                  24 passed
unittest:                24 passed
branch-aware coverage:  93% overall
mypy:                    no issues in 14 source/test files
compileall:              passed
editable install:        passed
wheel build:             passed
fresh offline wheel install: passed
fresh database doctor:   integrity OK
```

The wheel produced during acceptance was:

```text
moneyos-0.1.0.dev0-py3-none-any.whl
size: approximately 23 KB
```

It was deliberately built under `/tmp`, not committed as a source artifact.

## Environment decisions

Python 3.14 and Docker were available. `uv`, the `sqlite3` shell, Ruff, and a cached Python
container image were not available. The implementation therefore uses zero runtime
dependencies and did not depend on network downloads or an approval prompt. Existing local
pytest, coverage, and mypy installations provided extended validation.

An editable development environment exists at `.venv/` and is excluded by `.gitignore`.

## Known V0.1 boundaries

- One transaction contains one currency; foreign exchange is not modeled.
- Currency scale is two decimal places.
- One shared expense currently has one receivable party through the friendly API.
- Refunds reduce the selected personal expense category; reallocating a merchant refund
  against a shared-party receivable needs an explicit future workflow.
- Correction is currently reverse-then-record, not yet a single atomic replacement command.
- No reconciliation status, statement import, attachment storage, budget, UI, AI parser, or
  channel adapter exists yet.
- SQLite is not encrypted by MoneyOS; host disk and backup protection remain necessary.
- The existing `.git` directory is empty/read-only in this environment, so no commits were
  created.

These are explicit boundaries, not silently approximated behaviors.

## Recommended next work

The next implementation slice should be V0.2 Raw Inbox before adding a model:

1. raw-message ingestion API and CLI;
2. proposal schema that can express all current ledger workflows;
3. deterministic parsing for very simple messages;
4. confidence and confirmation state machine;
5. idempotency by `(channel, external_id)`;
6. parser/model provenance;
7. only then, a replaceable local/OpenAI-compatible provider interface.

Before real-data use, add account reconciliation and perform a restore drill with a copied
test ledger.
