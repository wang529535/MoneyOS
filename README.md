# MoneyOS

**Your finances. Your data. Your AI. Any hardware.**

MoneyOS is an AI-native, local-first personal finance intelligence platform. The current
V0.2 development version combines a reliable, auditable SQLite ledger with a raw inbox and
reviewable transaction proposals. It works without a cloud account or network connection.

> The ledger remembers what happened. The AI understands what it means.

The project vision is documented in
[`MoneyOS_Project_Vision_v0.1.md`](MoneyOS_Project_Vision_v0.1.md). The code in this repository
implements the first delivery gate, not the entire long-term product.

## What works now

- asset and liability accounts with exact opening balances;
- income and expense categories;
- ordinary expenses and income;
- transfers that never become spending;
- shared payments that separate cash paid, personal cost, and receivables;
- refunds and reimbursements linked to their original expenses;
- append-only reversals instead of destructive edits;
- balanced postings enforced before a transaction becomes visible;
- append-only audit history and preserved raw input;
- validated SQLite backup and non-overwriting restore;
- deterministic JSON and CSV exports;
- database integrity diagnostics;
- idempotent raw-message ingestion by channel and external message ID;
- conservative parsing of simple Chinese expenses, income, transfers, and shared payments;
- structured proposals with confidence, missing fields, parser version, and rationale;
- explicit confirmation/rejection and recoverable batch processing;
- zero runtime dependencies beyond Python 3.11+.

V0.2 does **not** yet bundle an LLM, dashboard, bank synchronization, or live message-channel
adapter. The parser protocol is replaceable, but the included parser is a deterministic,
fail-closed baseline. Future models will propose the same validated operations rather than
owning financial truth.

## Quick start

Run directly from the repository:

```bash
python3 -m moneyos --db my-ledger.db init
python3 -m moneyos --db my-ledger.db account add WeChat --opening 1000
python3 -m moneyos --db my-ledger.db category add Dining
python3 -m moneyos --db my-ledger.db expense \
  --account WeChat --category Dining --amount 26 --description "McDonald's"
python3 -m moneyos --db my-ledger.db account balances
python3 -m moneyos --db my-ledger.db category balances
```

## Raw inbox workflow

Add a message with an external ID supplied by its channel. Repeating the same channel and ID
is idempotent:

```bash
python3 -m moneyos --db my-ledger.db inbox add "麦当劳26" \
  --channel cli --external-id demo-001
```

The command prints a raw-message ID. Parse it into a reviewable proposal:

```bash
python3 -m moneyos --db my-ledger.db inbox parse RAW_MESSAGE_ID
python3 -m moneyos --db my-ledger.db inbox show RAW_MESSAGE_ID
```

Simple messages contain an amount but intentionally do not guess the payment account or
category. Supply those facts when confirming the proposal:

```bash
python3 -m moneyos --db my-ledger.db inbox confirm PROPOSAL_ID \
  --account WeChat --category Dining
```

Other supported baseline patterns include:

```text
妈妈给了500
从Bank转100到Cash
和小李吃海底捞我先付238，他后来转我100
```

The shared-payment example posts CNY 138 as personal dining cost, CNY 100 as a receivable,
then records the detected CNY 100 repayment. The original message is linked to the primary
expense and confirmation is safe to retry.

Parse all new pending messages or reject an incorrect proposal:

```bash
python3 -m moneyos --db my-ledger.db inbox parse --limit 50
python3 -m moneyos --db my-ledger.db inbox reject PROPOSAL_ID --reason "not a transaction"
python3 -m moneyos --db my-ledger.db inbox list --status failed
```

Failed messages are preserved and are not retried in every batch. After a parser or input
issue is addressed, retry one explicitly with `inbox parse RAW_MESSAGE_ID`.

Or install an editable development command without downloading dependencies:

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install --no-build-isolation -e .
.venv/bin/moneyos --version
```

If the virtual environment already contains `setuptools`, `--system-site-packages` is not
needed. Running `python3 -m moneyos` always remains available without installation.

## Common workflows

### Income and transfers

```bash
python3 -m moneyos --db my-ledger.db category add Salary --kind income
python3 -m moneyos --db my-ledger.db income \
  --account WeChat --category Salary --amount 500

python3 -m moneyos --db my-ledger.db account add Cash
python3 -m moneyos --db my-ledger.db transfer \
  --from WeChat --to Cash --amount 100
```

### Shared payment and reimbursement

Suppose you pay CNY 238, your share is CNY 138, and Xiao Li owes the remaining CNY 100:

```bash
python3 -m moneyos --db my-ledger.db expense \
  --account WeChat \
  --category Dining \
  --amount 238 \
  --personal-amount 138 \
  --owed-by "Xiao Li" \
  --description "Hotpot"
```

The command prints the expense transaction ID. Use it when the reimbursement arrives:

```bash
python3 -m moneyos --db my-ledger.db reimburse \
  --account WeChat \
  --party "Xiao Li" \
  --amount 100 \
  --of EXPENSE_TRANSACTION_ID
```

This creates no income. It increases WeChat cash and reduces `Receivable:Xiao Li`.

### Refund and reversal

```bash
python3 -m moneyos --db my-ledger.db refund \
  --account WeChat --category Dining --amount 26 --of EXPENSE_TRANSACTION_ID

python3 -m moneyos --db my-ledger.db transaction reverse TRANSACTION_ID \
  --reason "duplicate entry"
```

Posted records are never rewritten or deleted. Reverse any linked refund or reimbursement
before reversing its original expense.

### Audit, backup, export, and diagnostics

```bash
python3 -m moneyos --db my-ledger.db audit
python3 -m moneyos --db my-ledger.db doctor
python3 -m moneyos --db my-ledger.db backup backups/ledger-2026-09-06.db
python3 -m moneyos restore backups/ledger-2026-09-06.db --target restored.db
python3 -m moneyos --db my-ledger.db export --format json --output exports/ledger.json
python3 -m moneyos --db my-ledger.db export --format csv --output exports/postings.csv
```

Backup, restore, and export refuse to overwrite an existing destination.

## Why balanced postings?

MoneyOS records each transaction as a balanced group of signed postings. For a CNY 26 expense:

```text
Dining   +2600 minor units
WeChat   -2600 minor units
```

For a shared CNY 238 payment where the user's final cost is CNY 138:

```text
Dining                +13800
Receivable:Xiao Li    +10000
WeChat                -23800
```

This structure answers both “how much cash left?” and “what was my actual cost?” without
pretending a friend's repayment is income. See [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) for
the complete model.

## Tests

The baseline suite uses the standard library and requires no install:

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q moneyos tests
```

Tests create temporary databases and do not touch `moneyos.db` or real financial data.

When the optional tools are already available, the extended checks are:

```bash
python3 -m pytest -q
python3 -m mypy moneyos tests
python3 -m coverage run --branch -m unittest discover -s tests
python3 -m coverage report -m
```

## Documentation

- [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) — facts, posting conventions, invariants, and
  deferred decisions;
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — module boundaries, security, and extension
  seams;
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — testable gates from V0.1 through V1.0;
- [`docs/INBOX.md`](docs/INBOX.md) — raw-message lifecycle, proposal contract, and safety;
- [`docs/SECURITY.md`](docs/SECURITY.md) — current guarantees, limitations, and reporting;
- [`docs/ADR/0001-balanced-postings.md`](docs/ADR/0001-balanced-postings.md) — why the ledger
  uses balanced postings;
- [`docs/ADR/0002-standard-library-foundation.md`](docs/ADR/0002-standard-library-foundation.md) —
  why V0.1 has no runtime dependency.
- [`docs/ADR/0003-separate-raw-messages-and-proposals.md`](docs/ADR/0003-separate-raw-messages-and-proposals.md)
  — why parser output is not a ledger fact.

## Project principles

1. Ledger is truth.
2. AI is replaceable.
3. Freedom to analyze, discipline to act.
4. Everything important is auditable.
5. Preserve raw input.
6. Privacy by architecture.
7. Money serves life.

MoneyOS is at an early foundation stage. Do not yet use it as the sole copy of irreplaceable
financial records; keep tested backups and independently reconcile important balances.
