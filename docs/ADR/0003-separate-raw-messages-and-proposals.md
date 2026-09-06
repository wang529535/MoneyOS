# ADR 0003: Separate raw messages, proposals, and ledger facts

- Status: Accepted
- Date: 2026-09-06

## Context

Natural-language input is incomplete and sometimes wrong. Local rules and language models can
misclassify a transaction, omit an account, misunderstand multiple amounts, or change behavior
after an upgrade. Writing parser output directly into the ledger would make model confidence
an implicit form of financial authority.

Channel delivery is also at-least-once in many real integrations. A process can stop after a
ledger write but before acknowledging the external message, creating duplicate risk.

## Decision

MoneyOS represents three different objects:

1. `RawMessage` is immutable evidence of what a channel delivered.
2. `TransactionProposal` is immutable parser output plus provenance and review state.
3. A posted ledger transaction is the validated financial fact.

Every included V0.2 proposal requires explicit confirmation. Confirmation calls
`LedgerService`; parsers receive no database connection. Channel/external IDs deduplicate raw
delivery, and a unique transaction-to-raw-message link makes confirmation retryable after a
partial process failure.

Parsers receive a small `ParserContext` containing account and category names, not ledger
write access or unrestricted financial history.

## Consequences

Positive:

- raw text survives parser/model upgrades;
- confidence and model identity remain auditable;
- ambiguous input fails without polluting the ledger;
- confirmation can be retried without duplicating the primary transaction;
- channel, parser, and ledger lifecycles can evolve independently;
- future cloud parsers can be shown an explicit, minimal disclosure boundary.

Costs:

- an extra review step remains until proven rules qualify for opt-in auto-posting;
- the inbox and ledger use an idempotent recovery protocol instead of one long transaction;
- shared messages containing both payment and settlement may create two linked ledger
  transactions;
- rejected and failed records consume storage because evidence is append-only.

## Alternatives considered

### Parse and immediately write

Fast but unsafe, difficult to audit, and vulnerable to duplicate channel delivery. Rejected.

### Store only raw text and reparse on every query

Preserves input but makes financial facts model-dependent and unstable over time. Rejected.

### Give a model direct database write access

Conflicts with the MoneyOS principle “freedom to analyze, discipline to act.” Rejected.
