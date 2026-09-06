"""Replaceable transaction parser protocol and a safe deterministic baseline parser."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Protocol

from .errors import ValidationError
from .money import parse_minor_units


class ParseError(ValidationError):
    """A parser cannot produce a safe proposal from a message."""


@dataclass(frozen=True)
class ParseResult:
    kind: str
    payload: dict[str, Any]
    confidence: float
    missing_fields: tuple[str, ...]
    rationale: str
    parser_id: str
    parser_version: str
    model_id: str | None = None
    requires_confirmation: bool = True


@dataclass(frozen=True)
class ParserContext:
    """Minimal ledger vocabulary a parser may use without receiving database access."""

    default_currency: str
    accounts: tuple[str, ...]
    expense_categories: tuple[str, ...]
    income_categories: tuple[str, ...]


class TransactionParser(Protocol):
    parser_id: str
    parser_version: str
    model_id: str | None

    def parse(self, content: str, *, context: ParserContext | None = None) -> ParseResult: ...


class DeterministicParser:
    """Conservative parser for common short CNY messages.

    It intentionally does not infer categories or payment accounts. Those fields are supplied
    during confirmation until user-defined rules or a model provider exists.
    """

    parser_id = "moneyos.deterministic"
    parser_version = "1.0.0"
    model_id = None

    _amount_pattern = r"(?<![\d.])(\d+(?:\.\d{1,2})?)(?![\d.])"
    _amount_re = re.compile(_amount_pattern)
    _shared_paid_re = re.compile(
        rf"(?:我(?:先)?付(?:了)?|先付(?:了)?|总共(?:花|付)(?:了)?)\s*[:：]?\s*{_amount_pattern}"
    )
    _shared_repaid_re = re.compile(
        rf"(?:(?:他|她|对方)\s*)?(?:后来\s*)?"
        rf"(?:转(?:给)?我|还(?:给)?我)\s*[:：]?\s*{_amount_pattern}"
    )
    _party_re = re.compile(
        r"(?:和|跟)\s*([\u4e00-\u9fffA-Za-z0-9_]{1,20}?)(?:一起|吃|去|在)"
    )
    _transfer_re = re.compile(
        rf"^从\s*(.+?)\s*(?:转|取)\s*{_amount_pattern}\s*"
        r"(?:元|块|CNY)?\s*(?:到|至)\s*(.+?)$",
        re.IGNORECASE,
    )
    _income_markers = ("工资", "收入", "到账", "收到", "给了", "给我", "转给我")

    def parse(self, content: str, *, context: ParserContext | None = None) -> ParseResult:
        if not isinstance(content, str) or not content.strip():
            raise ParseError("message content cannot be empty")
        normalized = unicodedata.normalize("NFKC", content).strip()
        if len(normalized) > 100_000:
            raise ParseError("message content exceeds parser limit")
        if re.search(r"-\s*\d", normalized):
            raise ParseError("negative signed amounts are not accepted as natural-language records")
        if "退款" in normalized or "报销" in normalized:
            raise ParseError("refund and reimbursement messages require a linked manual workflow")

        shared = self._parse_shared(normalized)
        if shared:
            return shared
        transfer = self._parse_transfer(normalized)
        if transfer:
            return transfer

        matches = list(self._amount_re.finditer(normalized))
        if not matches:
            raise ParseError("no monetary amount found")
        if len(matches) != 1:
            raise ParseError("multiple amounts are ambiguous; manual review is required")
        amount_minor = parse_minor_units(matches[0].group(1))
        label = self._label_without_amount(normalized, matches[0])
        if any(marker in normalized for marker in self._income_markers):
            payee = self._income_party(normalized)
            return ParseResult(
                kind="income",
                payload={
                    "amount_minor": amount_minor,
                    "currency": "CNY",
                    "description": f"Income from {payee}" if payee else (label or "Income"),
                    "payee": payee,
                },
                confidence=0.72 if payee or "工资" in normalized else 0.62,
                missing_fields=("account", "category"),
                rationale="income marker and one exact amount recognized",
                parser_id=self.parser_id,
                parser_version=self.parser_version,
            )
        return ParseResult(
            kind="expense",
            payload={
                "amount_minor": amount_minor,
                "personal_minor": amount_minor,
                "currency": "CNY",
                "description": label or "Expense",
                "payee": label or None,
            },
            confidence=0.72 if label else 0.52,
            missing_fields=("account", "category"),
            rationale="one exact amount recognized; no income or transfer marker found",
            parser_id=self.parser_id,
            parser_version=self.parser_version,
        )

    def _parse_shared(self, content: str) -> ParseResult | None:
        paid = self._shared_paid_re.search(content)
        repaid = self._shared_repaid_re.search(content)
        if not paid or not repaid:
            return None
        paid_minor = parse_minor_units(paid.group(1))
        repaid_minor = parse_minor_units(repaid.group(1))
        if repaid_minor > paid_minor:
            raise ParseError("reimbursement is greater than the detected payment")
        party_match = self._party_re.search(content)
        party = party_match.group(1).strip() if party_match else None
        missing = ("account", "category") + (() if party else ("owed_by",))
        description = content[: paid.start()].strip(" ,，。:：") or "Shared expense"
        return ParseResult(
            kind="expense",
            payload={
                "amount_minor": paid_minor,
                "personal_minor": paid_minor - repaid_minor,
                "settled_minor": repaid_minor,
                "owed_by": party,
                "currency": "CNY",
                "description": description,
            },
            confidence=0.86 if party else 0.72,
            missing_fields=missing,
            rationale="advance payment and later reimbursement were both recognized",
            parser_id=self.parser_id,
            parser_version=self.parser_version,
        )

    def _parse_transfer(self, content: str) -> ParseResult | None:
        match = self._transfer_re.match(content)
        if not match:
            return None
        origin, amount, target = match.group(1).strip(), match.group(2), match.group(3).strip()
        if not origin or not target:
            raise ParseError("transfer account names are incomplete")
        return ParseResult(
            kind="transfer",
            payload={
                "from_account": origin,
                "to_account": target,
                "amount_minor": parse_minor_units(amount),
                "currency": "CNY",
                "description": f"Transfer from {origin} to {target}",
            },
            confidence=0.9,
            missing_fields=(),
            rationale="explicit from-account, amount, and to-account pattern recognized",
            parser_id=self.parser_id,
            parser_version=self.parser_version,
        )

    @staticmethod
    def _label_without_amount(content: str, match: re.Match[str]) -> str:
        combined = (content[: match.start()] + " " + content[match.end() :]).strip()
        combined = re.sub(r"\b(?:CNY|RMB)\b", "", combined, flags=re.IGNORECASE)
        combined = combined.strip(" ,，。:：元块")
        return re.sub(r"\s+", " ", combined)

    @staticmethod
    def _income_party(content: str) -> str | None:
        match = re.match(r"^(.{1,40}?)(?:给了?我?|转给我|还给我)", content)
        if match:
            party = match.group(1).strip(" ,，。:：")
            return party or None
        return None
