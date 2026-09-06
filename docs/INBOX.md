# MoneyOS V0.2 Raw Inbox and Proposal Model

Status: implemented
Last updated: 2026-09-06

## 1. Purpose

The inbox separates untrusted human/channel text from financial truth. Receiving a message is
not the same as recording a transaction. Parsing creates a proposal; only validated
confirmation invokes the ledger service.

```text
Channel message
      |
      v
immutable RawMessage
      |
      v
replaceable parser
      |
      v
immutable TransactionProposal
      |
 explicit review / missing-field completion
      |
      v
LedgerService -> balanced posted transaction
```

## 2. Message lifecycle

```text
pending  -> proposed -> confirmed
                    \-> rejected
    |
    \-> failed -> explicit retry -> proposed/failed
```

Batch parsing selects only `pending` records. A permanently failed message therefore does not
consume work on every batch. It can be retried explicitly after a parser upgrade or other
operator action.

Raw content, channel, external ID, receipt time, and message identity are immutable. Resolved
confirmed/rejected messages are terminal. Failed messages retain a safe error description and
parser provenance.

## 3. Idempotency

Channel adapters should provide a stable external message ID. The pair
`(channel, external_id)` is unique:

- ingesting the same pair and exact content returns the existing message;
- ingesting the same pair with different content raises a conflict;
- messages without external IDs are treated as separate observations.

A posted primary transaction has a unique `raw_message_id`. If the process stops after ledger
posting but before proposal confirmation, retry finds the existing transaction and completes
the inbox state transition instead of posting again.

For a shared message that also says the other party already repaid, the primary expense is
posted first and linked reimbursement completion is checked on retry. This gives the same
eventual result without duplicate reimbursements.

## 4. Proposal contract

A proposal stores:

- transaction kind;
- JSON payload in integer minor units;
- confidence from zero to one;
- missing fields;
- whether confirmation is required;
- parser ID and version;
- optional model ID;
- short rationale;
- attempt number and timestamps;
- terminal review decision and resulting transaction ID.

Payload and provenance are immutable. A review decision changes only review/status fields.
Rejected proposals remain available for audit.

V0.2 proposal kinds are `expense`, `income`, and `transfer`. Refunds and reimbursements that
arrive as standalone messages require an explicit link to an original transaction and are
therefore rejected by the deterministic parser rather than guessed.

## 5. Included deterministic parser

The baseline parser supports short CNY inputs with at most two decimal places:

```text
麦当劳26
妈妈给了500
从Bank转100到Cash
和小李吃海底捞我先付238，他后来转我100
```

It normalizes full-width characters for parsing but preserves the exact raw input. It does not
guess accounts or categories. Multiple unexplained amounts, negative signed amounts,
standalone refund/reimbursement text, missing amounts, and impossible shared-payment math fail
closed.

The deterministic parser is a safety baseline, not the final AI capability.

## 6. Parser replacement

Any future local or cloud parser implements `TransactionParser` and returns `ParseResult`.
Inbox validation rejects unsupported kinds, invalid/non-finite confidence, impossible shared
splits, non-integer monetary fields, and non-JSON payloads before proposal persistence.

A model implementation receives no database connection. It cannot post, update, or delete
financial facts. Model ID and parser version are stored with every proposal and raw-message
processing result.

## 7. Confirmation

Confirmation fills facts that parsing could not safely infer:

- expense/income account;
- expense/income category;
- optional shared-party identity;
- optional occurrence date or corrected description;
- transfer accounts when absent from the parsed payload.

The ledger service repeats all accounting, account-role, currency, amount, and date validation.
A valid proposal is not a bypass around ledger rules.

## 8. Current boundaries

- All included parser proposals require explicit confirmation.
- The baseline assumes CNY and does not parse exchange rates.
- There are no user-defined merchant rules yet.
- There is no live Feishu/Telegram adapter yet; CLI simulates channel ingestion.
- There is no bundled local or cloud LLM provider yet.
- The primary ledger post and final inbox status use an idempotent recovery protocol rather
  than one long SQLite transaction, keeping slow/future parsers outside ledger locks.

These boundaries should be addressed incrementally without weakening the ledger authority
model.
