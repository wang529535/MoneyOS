"""Small immutable read models used by services and presentation layers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Account:
    id: str
    name: str
    kind: str
    role: str
    currency: str
    archived: bool
    created_at: str


@dataclass(frozen=True)
class AccountBalance:
    account: Account
    raw_minor: int
    balance_minor: int


@dataclass(frozen=True)
class Posting:
    id: int
    transaction_id: str
    account_id: str
    account_name: str
    amount_minor: int
    memo: str | None


@dataclass(frozen=True)
class Transaction:
    id: str
    kind: str
    amount_minor: int
    currency: str
    occurred_on: str
    description: str
    payee: str | None
    status: str
    raw_input: str | None
    actor: str
    source: str
    created_at: str
    reversed_by_id: str | None
    related: tuple[dict[str, str], ...] = ()
    postings: tuple[Posting, ...] = ()
    metadata: dict[str, Any] | None = None
