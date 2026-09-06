# ADR 0001: Use balanced postings as the ledger core

- Status: Accepted
- Date: 2026-09-06

## Context

MoneyOS must distinguish expenses from transfers, represent liability accounts, preserve the
difference between merchant payment and personal cost, and support refunds, reimbursements,
and corrections without rewriting history.

A single row containing `amount`, `source_account`, and `category` handles ordinary expenses
but becomes ambiguous for shared payments and linked settlements. Adding special columns for
every new case would spread accounting rules across the schema and analytics code.

## Decision

Each posted transaction contains two or more signed postings whose integer minor-unit amounts
sum to zero. Accounts include user assets/liabilities, income/expense categories, receivables,
and controlled system equity. Posting signs follow debit-positive convention internally.

Transactions are immutable after posting. Corrections append an exact reversal and, when
needed in a future workflow, a replacement transaction.

## Consequences

Positive:

- transfers cannot accidentally become spending;
- account, category, and receivable facts reconcile arithmetically;
- refunds and reimbursements naturally reduce the correct balance;
- liability accounts require no special transaction table;
- migrations can extend account roles without replacing transaction history.

Costs:

- the internal model requires accounting sign conventions;
- CLI/reporting code must convert normal credit balances for friendly display;
- service workflows are needed so users and AI never have to construct raw postings;
- multi-currency transactions still require a future exchange-rate design.

## Alternatives considered

### One transaction row with source/destination/category columns

Simpler initially, but shared payments require extra exceptions and transfers/refunds become
different shapes. Rejected as a long-term lock-in risk.

### Full enterprise general ledger

Powerful but would introduce journals, periods, reconciliation states, and accounting controls
beyond the first user's needs. Rejected for V0.1 as overengineering.

The accepted approach keeps the balanced mathematical core while exposing small personal-
finance workflows.
