# MoneyOS Implementation Roadmap

This roadmap translates the project vision into testable delivery gates. Dates are not fixed;
each version advances only after its core behavior works with real data.

## V0.1 — Ledger Foundation

- balanced SQLite ledger;
- accounts and income/expense categories;
- expense, income, transfer, refund, reimbursement, and reversal workflows;
- audit log and raw-input preservation;
- CLI;
- backup, restore, JSON and CSV export;
- migrations and automated tests.

Exit gate: one user can safely keep a real ledger through the CLI and recover it from backup.

## V0.2 — AI Bookkeeping

- raw inbox lifecycle;
- model-provider interface and capability detection;
- structured transaction proposals;
- confidence thresholds and confirmation flow;
- batch parsing and parser provenance;
- deterministic fallback for simple inputs.

Exit gate: common natural-language records become correct ledger calls, while ambiguous input
never silently becomes a fact.

## V0.3 — Personal Dashboard

- local web UI;
- monthly/yearly spending and cash flow;
- account and category views;
- merchant summaries and calendar heatmap;
- budgets and base charts.

Exit gate: the product is convenient enough for continuous personal use.

## V0.4 — Finance Copilot

- natural-language queries;
- safe, read-only query planner;
- documented analytics views;
- table, chart, and Markdown report responses;
- fact/inference/advice labeling.

Exit gate: open-ended questions can be answered from deterministic query results without AI
inventing numbers.

## V0.5 — Semantic Finance

- people and organizations;
- relationships;
- events, contexts, and goals;
- entity resolution and aliases;
- richer shared-payment and reimbursement relations.

Exit gate: MoneyOS can reliably answer cross-dimensional questions about money, people, and
life events.

## V0.6 — Channels

- channel adapter contract;
- at least one reliable message-buffering channel;
- offline inbox synchronization;
- idempotency and delivery receipts;
- explicit privacy/data-flow indicators.

## V1.0 — Stable open-source product

- stable schema and migrations;
- provider and channel abstractions;
- Docker distribution;
- restore drills, security documentation, and contributor documentation;
- polished demo using semantic questions rather than ordinary dashboard screenshots.

Later versions add dynamic analytics, long-term memory, proactive insight, and an always-on
home-server mode without changing ownership of financial truth.
