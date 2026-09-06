# MoneyOS V0.1 Data Model

Status: accepted for the first implementation  
Scope: V0.1 Ledger Foundation  
Last updated: 2026-09-06

## 1. Goals

The V0.1 model must make the following facts unambiguous:

- where money is held or owed;
- whether a record is an expense, income, transfer, refund, reimbursement, or reversal;
- the difference between cash paid and the user's final cost;
- how a correction relates to the original record;
- who or what created every mutation;
- whether every posted transaction is arithmetically balanced.

The model deliberately does not attempt to represent every future semantic concept. People,
events, goals, AI-derived knowledge, multi-currency exchange, investment lots, and budgeting
rules remain outside the V0.1 execution path, but the transaction and link boundaries leave
room for them.

## 2. Core decision: balanced postings

MoneyOS stores a transaction as one immutable header plus two or more postings. Posting
amounts use debit-positive signs and must sum to zero inside one currency.

Examples:

```text
Expense, CNY 26
  Dining                 +2600
  Wallet                 -2600

Income, CNY 500
  Wallet                +50000
  Allowance             -50000

Transfer, CNY 100
  Cash                  +10000
  Bank                  -10000
```

The signs are an internal accounting convention. CLI output presents familiar positive
balances and amounts to the user.

This decision prevents transfers from becoming expenses and lets refunds and reimbursements
reduce the correct historical cost without rewriting the original record.

## 3. Money representation

Money is stored as integer minor units:

```text
CNY 26.00 -> 2600
```

Floating-point values are never used for ledger arithmetic. V0.1 supports currencies with a
two-decimal minor unit and requires every posting in a transaction to use the same currency.
Cross-currency transfers are deferred until an exchange-rate model is designed.

## 4. Accounts

All postings point to an account. Accounts have two independent classifications.

### 4.1 Account kind

| Kind | Meaning | Normal balance |
|---|---|---:|
| `asset` | Cash, bank, stored-value balance | debit / positive postings |
| `liability` | Credit card or money owed | credit / negative postings |
| `income` | Salary, allowance, other income category | credit / negative postings |
| `expense` | Dining, transport, travel category | debit / positive postings |
| `equity` | Opening balances and controlled adjustments | credit / negative postings |
| `receivable` | Money another party owes the user | debit / positive postings |

### 4.2 Account role

| Role | Meaning |
|---|---|
| `user` | A user-facing asset or liability account |
| `category` | An income or expense category backed by a ledger account |
| `party` | A receivable associated with a person or organization |
| `system` | Opening balance or other internal balancing account |

Keeping kind and role separate lets the ledger remain balanced while the product still shows
users familiar concepts such as Accounts and Categories.

Account names are unique in V0.1. Archived accounts remain queryable and cannot silently
disappear from historical reports.

## 5. Transactions

A transaction header contains:

- stable UUID;
- kind;
- positive display amount in minor units;
- currency;
- occurrence date;
- description and optional payee;
- lifecycle status (`draft` or `posted`);
- optional raw user input;
- actor and source channel;
- immutable creation timestamp;
- optional metadata JSON for non-authoritative display context.

Supported V0.1 kinds:

```text
opening
expense
income
transfer
refund
reimbursement
reversal
adjustment
```

A transaction is inserted as `draft`, receives its postings, is checked for balance, and is
then posted inside one SQLite transaction. Drafts are never returned by normal ledger
queries. Posted postings cannot be edited or deleted.

## 6. Transaction patterns

### 6.1 Ordinary expense

The user pays CNY 238 from WeChat for dining:

```text
Dining                +23800
WeChat                -23800
```

Cash paid and personal cost are both CNY 238.

### 6.2 Shared expense / advance payment

The user pays CNY 238; their own share is CNY 138 and Xiao Li owes CNY 100:

```text
Dining                +13800
Receivable:Xiao Li    +10000
WeChat                -23800
```

This preserves three different facts:

- merchant payment: CNY 238;
- personal expense: CNY 138;
- outstanding receivable: CNY 100.

When Xiao Li repays CNY 100:

```text
WeChat                +10000
Receivable:Xiao Li    -10000
```

The repayment is linked to the original expense with `reimbursement_of`. It changes cash and
settles the receivable but does not create income.

### 6.3 Refund

A CNY 26 refund to a bank account:

```text
Bank                   +2600
Dining                 -2600
```

It links to the original expense with `refund_of`, reducing net category spending.

### 6.4 Transfer

Move CNY 100 from a bank account to cash:

```text
Cash                  +10000
Bank                  -10000
```

No income or expense account is touched, so cash-flow and spending reports cannot mistake the
transfer for consumption.

### 6.5 Reversal

Posted financial history is corrected by appending a reversal rather than updating or
deleting postings. A reversal copies every original posting with the opposite sign and links
back with `reversal_of`.

The original transaction records `reversed_by_id` for convenient display. Both records remain
in the audit trail. A future correction workflow can atomically create a reversal and a
replacement transaction.

## 7. Transaction links

Links are directional and typed:

```text
refund_of
reimbursement_of
reversal_of
correction_of
```

The database prevents duplicate links. Services validate that linked transactions use a
compatible currency and relation.

## 8. Audit log

Every business mutation appends an audit record with:

- action;
- entity type and ID;
- actor;
- source;
- timestamp;
- reason where relevant;
- before and after JSON snapshots.

Audit records cannot be updated or deleted through the application database connection.
Financial audit entries are evidence, not a second ledger: balances always come from postings.

## 9. Raw messages

The schema reserves a `raw_messages` table for V0.2. It stores channel identity, external
message identity, original content, receipt time, processing status, parser/model metadata,
and confidence. A transaction may reference a raw message, but raw messages never become
financial facts until a validated transaction is posted.

## 10. Database invariants

The database and service layer jointly enforce:

1. posted transactions have at least two postings;
2. all postings in a posted transaction sum to zero;
3. all accounts in one transaction use the transaction currency;
4. monetary amounts are integers and display amounts are positive;
5. account names are unique;
6. posted postings are immutable;
7. audit records are append-only;
8. reversal links are one-to-one for an original transaction;
9. normal ledger reads exclude drafts;
10. foreign-key checking is enabled for every connection.

Some cross-row invariants cannot be expressed as ordinary SQLite `CHECK` constraints. They
are validated before posting, with a database trigger acting as a final balance guard.

## 11. Balance calculation

Raw balance is the sum of all posted postings for an account. User-facing balance applies the
normal sign:

```text
asset / expense / receivable -> raw balance
liability / income / equity  -> -raw balance
```

Consequently, a credit-card debt of CNY 500 and salary income of CNY 500 are displayed as
positive CNY 500 even though their internal posting totals are negative.

## 12. Deferred decisions

The following require separate design and are intentionally not improvised in V0.1:

- currencies with zero or three decimal places;
- foreign-exchange gains, rates, and cross-currency transfers;
- investment lots and market valuation;
- split tender across currencies;
- multi-user ownership and household permissions;
- formal entity/person/event/goal tables;
- budget periods and rollover rules;
- attachment storage;
- bank-import deduplication.

Deferring these features keeps V0.1 small without requiring destructive changes to the core
transaction/posting boundary.
