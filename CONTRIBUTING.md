# Contributing to MoneyOS

MoneyOS is still in its foundation stage. Changes should preserve the distinction between
financial facts, deterministic computation, and AI interpretation.

## Local checks

```bash
python3 -m compileall -q moneyos tests
python3 -m unittest discover -s tests -v
```

No network access or third-party package is required for the baseline suite.

## Change expectations

- Add or update tests for every accounting rule.
- Store money as integer minor units; do not introduce floats into ledger code.
- Use parameterized SQL.
- Never mutate or delete posted postings.
- Implement corrections as reversals plus replacement facts.
- Keep AI/model code outside the ledger authority boundary.
- Add a migration for persistent schema changes after V0.1 is released.
- Record consequential architectural decisions in `docs/ADR/`.

Before opening the project to public contributions, this guide still needs the repository URL,
code of conduct, review policy, release process, and security contact.
