# MoneyOS V0.2 Work Report — 2026-09-06

## Outcome

MoneyOS now has a complete raw-message-to-ledger review loop on top of the V0.1 balanced
ledger. The included parser is deterministic and conservative; the parser interface is ready
for future local or cloud implementations without giving them ledger authority.

## Delivered

- Schema migration v2, including a tested upgrade from a populated V0.1 inbox table.
- Immutable raw messages and immutable structured proposal payloads.
- Channel/external-message idempotency.
- Parser protocol, minimal parser context, version/model provenance, confidence, rationale, and
  missing-field records.
- Deterministic parsing for simple Chinese expenses, income, explicit transfers, and a shared
  expense containing an already-received repayment.
- Fail-closed behavior for ambiguous amounts, negative signs, standalone refund/reimbursement
  text, invalid confidence, impossible splits, and malformed provider output.
- Explicit confirm/reject lifecycle and terminal-state database guards.
- Batch parsing that continues past failures and does not repeatedly process failed messages.
- Confirmation recovery after a ledger post using unique `raw_message_id` linkage.
- New CLI routes for inbox add/list/parse/show/confirm/reject.
- JSON export and `doctor` awareness of inbox/proposal state.

## Acceptance scenario

The following real CLI flow was completed:

```text
和小李吃海底捞我先付238，他后来转我100
```

Result:

```text
parsed gross payment:       CNY 238
personal dining cost:       CNY 138
party receivable created:   CNY 100
repayment recorded:         CNY 100
final receivable:           CNY 0
cash change:               -CNY 138
inbox status:               confirmed
unbalanced transactions:    0
inbox inconsistencies:      0
```

## Explicit boundaries

- No LLM is bundled yet. “AI Bookkeeping Foundation” means the safe proposal boundary is now
  implemented, not that arbitrary language is understood.
- All current proposals require explicit confirmation.
- The deterministic parser assumes CNY.
- Account/category rules and model capability routing remain future work.
- Live Feishu/Telegram adapters are not included yet.

## Verification

```text
pytest:                  45 passed
unittest:                45 passed
branch-aware coverage:  92% overall
mypy:                    no issues in 20 source/test files
compileall:              passed
real CLI inbox flow:     passed
schema migration:        V1 -> V2 passed
doctor:                  ledger and inbox integrity OK
wheel build/install:     moneyos-0.2.0.dev0, approximately 35 KB, passed
```

## Recommended next slice

Add user-defined deterministic classification rules and defaults before connecting an LLM.
That will let messages such as `麦当劳26` fill a proven category/account locally, lower model
usage, and create a safe basis for opt-in high-confidence auto-posting.
