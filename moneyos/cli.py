"""Command-line interface for the MoneyOS V0.1 ledger."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from . import __version__, db
from .errors import MoneyOSError, ValidationError
from .export import export_database
from .inbox import InboxService
from .money import format_minor_units, parse_minor_units
from .service import LedgerService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="moneyos",
        description="Local-first, auditable personal finance ledger",
    )
    parser.add_argument("--db", default="moneyos.db", help="SQLite database path")
    parser.add_argument("--version", action="version", version=f"MoneyOS {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="initialize or migrate the database")

    account = subparsers.add_parser("account", help="manage user accounts")
    account_sub = account.add_subparsers(dest="account_command", required=True)
    account_add = account_sub.add_parser("add", help="add an asset or liability account")
    account_add.add_argument("name")
    account_add.add_argument("--kind", choices=("asset", "liability"), default="asset")
    account_add.add_argument("--currency", default="CNY")
    account_add.add_argument("--opening", default="0.00")
    account_sub.add_parser("list", help="list user accounts")
    account_sub.add_parser("balances", help="show user account balances")

    category = subparsers.add_parser("category", help="manage income and expense categories")
    category_sub = category.add_subparsers(dest="category_command", required=True)
    category_add = category_sub.add_parser("add", help="add a category")
    category_add.add_argument("name")
    category_add.add_argument("--kind", choices=("expense", "income"), default="expense")
    category_add.add_argument("--currency", default="CNY")
    category_sub.add_parser("list", help="list categories")
    category_sub.add_parser("balances", help="show net category totals")

    expense = subparsers.add_parser("expense", help="record an expense or shared payment")
    _common_record_arguments(expense)
    expense.add_argument("--account", required=True)
    expense.add_argument("--category", required=True)
    expense.add_argument("--amount", required=True, help="total amount paid")
    expense.add_argument("--personal-amount", help="your final share of a shared payment")
    expense.add_argument("--owed-by", help="party owing the difference")
    expense.add_argument("--payee")

    income = subparsers.add_parser("income", help="record income")
    _common_record_arguments(income)
    income.add_argument("--account", required=True)
    income.add_argument("--category", required=True)
    income.add_argument("--amount", required=True)
    income.add_argument("--payee")

    transfer = subparsers.add_parser("transfer", help="transfer between accounts")
    _common_record_arguments(transfer)
    transfer.add_argument("--from", dest="from_account", required=True)
    transfer.add_argument("--to", dest="to_account", required=True)
    transfer.add_argument("--amount", required=True)

    refund = subparsers.add_parser("refund", help="record a refund linked to an expense")
    refund.add_argument("--account", required=True)
    refund.add_argument("--category", required=True)
    refund.add_argument("--amount", required=True)
    refund.add_argument("--of", dest="original", required=True, help="original expense ID")
    refund.add_argument("--date")
    refund.add_argument("--description")

    reimburse = subparsers.add_parser(
        "reimburse", help="settle a receivable from a shared payment"
    )
    reimburse.add_argument("--account", required=True)
    reimburse.add_argument("--party", required=True)
    reimburse.add_argument("--amount", required=True)
    reimburse.add_argument("--of", dest="original", required=True, help="original expense ID")
    reimburse.add_argument("--date")
    reimburse.add_argument("--description")

    transaction = subparsers.add_parser("transaction", help="inspect or reverse transactions")
    transaction_sub = transaction.add_subparsers(dest="transaction_command", required=True)
    transaction_list = transaction_sub.add_parser("list", help="list posted transactions")
    transaction_list.add_argument("--limit", type=int, default=50)
    transaction_list.add_argument("--kind")
    transaction_show = transaction_sub.add_parser("show", help="show one transaction")
    transaction_show.add_argument("id")
    transaction_reverse = transaction_sub.add_parser(
        "reverse", help="append an exact reversal; never deletes history"
    )
    transaction_reverse.add_argument("id")
    transaction_reverse.add_argument("--reason", required=True)
    transaction_reverse.add_argument("--date")

    audit = subparsers.add_parser("audit", help="show append-only audit records")
    audit.add_argument("--limit", type=int, default=100)

    backup = subparsers.add_parser("backup", help="create a validated SQLite backup")
    backup.add_argument("destination")

    restore = subparsers.add_parser(
        "restore", help="restore a backup to a new target without overwriting"
    )
    restore.add_argument("source")
    restore.add_argument("--target", required=True)

    export = subparsers.add_parser("export", help="export posted facts")
    export.add_argument("--format", choices=("json", "csv"), required=True)
    export.add_argument("--output", required=True)

    inbox = subparsers.add_parser("inbox", help="ingest, parse, and review raw messages")
    inbox_sub = inbox.add_subparsers(dest="inbox_command", required=True)
    inbox_add = inbox_sub.add_parser("add", help="append a raw message to the inbox")
    inbox_add.add_argument("content")
    inbox_add.add_argument("--channel", default="cli")
    inbox_add.add_argument("--external-id")
    inbox_list = inbox_sub.add_parser("list", help="list raw messages")
    inbox_list.add_argument("--status", choices=(
        "pending", "proposed", "confirmed", "rejected", "failed"
    ))
    inbox_list.add_argument("--limit", type=int, default=100)
    inbox_parse = inbox_sub.add_parser("parse", help="parse one message or a pending batch")
    inbox_parse.add_argument("id", nargs="?")
    inbox_parse.add_argument("--limit", type=int, default=50)
    inbox_show = inbox_sub.add_parser("show", help="show a raw message and all proposals")
    inbox_show.add_argument("id")
    inbox_confirm = inbox_sub.add_parser("confirm", help="validate and post a proposal")
    inbox_confirm.add_argument("id", help="proposal ID")
    inbox_confirm.add_argument("--account")
    inbox_confirm.add_argument("--category")
    inbox_confirm.add_argument("--from", dest="from_account")
    inbox_confirm.add_argument("--to", dest="to_account")
    inbox_confirm.add_argument("--owed-by")
    inbox_confirm.add_argument("--date")
    inbox_confirm.add_argument("--description")
    inbox_reject = inbox_sub.add_parser("reject", help="reject a proposal without posting")
    inbox_reject.add_argument("id", help="proposal ID")
    inbox_reject.add_argument("--reason", required=True)

    doctor = subparsers.add_parser("doctor", help="validate database integrity and invariants")
    doctor.add_argument("--json", action="store_true", dest="as_json")
    return parser


def _common_record_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--date", help="occurrence date in YYYY-MM-DD format")
    parser.add_argument("--description")
    parser.add_argument("--raw", help="preserve the original user message")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    service = LedgerService(args.db)
    try:
        return _dispatch(args, service)
    except (MoneyOSError, sqlite3.Error) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


def _dispatch(args: argparse.Namespace, service: LedgerService) -> int:
    if args.command == "init":
        version = service.initialize()
        print(f"Initialized {Path(args.db)} (schema v{version})")
        return 0

    if args.command == "account":
        if args.account_command == "add":
            account = service.create_account(
                args.name,
                kind=args.kind,
                currency=args.currency,
                opening_minor=parse_minor_units(args.opening, allow_zero=True),
            )
            print(f"Created {account.kind} account {account.name} [{account.id}]")
        elif args.account_command == "list":
            _print_accounts(service.accounts(role="user"))
        else:
            _print_balances(service.balances(role="user"))
        return 0

    if args.command == "category":
        if args.category_command == "add":
            category = service.create_category(
                args.name, kind=args.kind, currency=args.currency
            )
            print(f"Created {category.kind} category {category.name} [{category.id}]")
        elif args.category_command == "list":
            _print_accounts(service.accounts(role="category"))
        else:
            _print_balances(service.balances(role="category"))
        return 0

    if args.command == "expense":
        amount = parse_minor_units(args.amount)
        personal = (
            parse_minor_units(args.personal_amount, allow_zero=True)
            if args.personal_amount is not None
            else None
        )
        transaction_id = service.record_expense(
            account=args.account,
            category=args.category,
            amount_minor=amount,
            personal_minor=personal,
            owed_by=args.owed_by,
            occurred_on=args.date,
            description=args.description,
            payee=args.payee,
            raw_input=args.raw,
        )
        _print_recorded(service, transaction_id)
        return 0

    if args.command == "income":
        transaction_id = service.record_income(
            account=args.account,
            category=args.category,
            amount_minor=parse_minor_units(args.amount),
            occurred_on=args.date,
            description=args.description,
            payee=args.payee,
            raw_input=args.raw,
        )
        _print_recorded(service, transaction_id)
        return 0

    if args.command == "transfer":
        transaction_id = service.record_transfer(
            from_account=args.from_account,
            to_account=args.to_account,
            amount_minor=parse_minor_units(args.amount),
            occurred_on=args.date,
            description=args.description,
            raw_input=args.raw,
        )
        _print_recorded(service, transaction_id)
        return 0

    if args.command == "refund":
        transaction_id = service.record_refund(
            account=args.account,
            category=args.category,
            amount_minor=parse_minor_units(args.amount),
            original_transaction_id=args.original,
            occurred_on=args.date,
            description=args.description,
        )
        _print_recorded(service, transaction_id)
        return 0

    if args.command == "reimburse":
        transaction_id = service.record_reimbursement(
            account=args.account,
            party=args.party,
            amount_minor=parse_minor_units(args.amount),
            original_transaction_id=args.original,
            occurred_on=args.date,
            description=args.description,
        )
        _print_recorded(service, transaction_id)
        return 0

    if args.command == "transaction":
        if args.transaction_command == "list":
            _print_transactions(service.transactions(limit=args.limit, kind=args.kind))
        elif args.transaction_command == "show":
            _print_transaction(service.transaction(args.id))
        else:
            transaction_id = service.reverse_transaction(
                args.id, reason=args.reason, occurred_on=args.date
            )
            print(f"Reversal posted: {transaction_id}")
        return 0

    if args.command == "audit":
        rows = service.audit(limit=args.limit)
        if not rows:
            print("No audit records.")
        for row in rows:
            reason = f" reason={row['reason']}" if row["reason"] else ""
            print(
                f"{row['id']:>5} {row['created_at']} {row['action']:<15} "
                f"{row['entity_type']}:{row['entity_id']} actor={row['actor']}{reason}"
            )
        return 0

    if args.command == "backup":
        output = db.backup_database(args.db, args.destination)
        print(f"Validated backup created: {output}")
        return 0

    if args.command == "restore":
        output = db.restore_database(args.source, args.target)
        print(f"Validated database restored: {output}")
        return 0

    if args.command == "export":
        output = export_database(args.db, args.output, format=args.format)
        print(f"Exported {args.format.upper()}: {output}")
        return 0

    if args.command == "inbox":
        inbox_service = InboxService(args.db)
        if args.inbox_command == "add":
            message, created = inbox_service.ingest(
                args.content, channel=args.channel, external_id=args.external_id
            )
            verb = "Ingested" if created else "Already ingested"
            print(f"{verb} raw message [{message.id}] status={message.status}")
        elif args.inbox_command == "list":
            _print_inbox_messages(
                inbox_service.messages(status=args.status, limit=args.limit)
            )
        elif args.inbox_command == "parse":
            if args.id:
                proposal = inbox_service.parse_message(args.id)
                _print_proposal(proposal)
            else:
                result = inbox_service.parse_pending(limit=args.limit)
                for proposal in result.proposals:
                    _print_proposal(proposal)
                for message_id, error in result.failures:
                    print(f"Failed {message_id}: {error}", file=sys.stderr)
                print(
                    f"Parsed {len(result.proposals)} message(s); "
                    f"{len(result.failures)} failed"
                )
        elif args.inbox_command == "show":
            message = inbox_service.message(args.id)
            payload = {
                "message": asdict(message),
                "proposals": [
                    asdict(item) for item in inbox_service.proposals_for_message(message.id)
                ],
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        elif args.inbox_command == "confirm":
            transaction_id = inbox_service.confirm(
                args.id,
                account=args.account,
                category=args.category,
                from_account=args.from_account,
                to_account=args.to_account,
                owed_by=args.owed_by,
                occurred_on=args.date,
                description=args.description,
            )
            print(f"Proposal confirmed; transaction posted: {transaction_id}")
        else:
            inbox_service.reject(args.id, reason=args.reason)
            print(f"Proposal rejected: {args.id}")
        return 0

    if args.command == "doctor":
        report = _doctor(args.db)
        if args.as_json:
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(f"Database: {report['database']}")
            print(f"Schema: v{report['schema_version']}")
            print(f"Transactions: {report['posted_transactions']}")
            print(f"Drafts: {report['draft_transactions']}")
            print(f"Unbalanced: {report['unbalanced_transactions']}")
            print(f"Currency mismatches: {report['currency_mismatches']}")
            print(f"Invalid reversal markers: {report['invalid_reversal_markers']}")
            print(f"Inbox messages: {report['inbox_messages']}")
            print(f"Open proposals: {report['open_proposals']}")
            print(f"Inbox inconsistencies: {report['inbox_inconsistencies']}")
            print("Integrity: OK")
        return 0

    raise ValidationError(f"unknown command: {args.command}")


def _print_accounts(accounts) -> None:
    if not accounts:
        print("No records.")
        return
    print(f"{'NAME':<30} {'KIND':<12} {'ROLE':<10} {'CURRENCY':<8} ID")
    for account in accounts:
        print(
            f"{account.name:<30} {account.kind:<12} {account.role:<10} "
            f"{account.currency:<8} {account.id}"
        )


def _print_balances(balances) -> None:
    if not balances:
        print("No records.")
        return
    print(f"{'NAME':<30} {'KIND':<12} {'BALANCE':>18}")
    for item in balances:
        print(
            f"{item.account.name:<30} {item.account.kind:<12} "
            f"{format_minor_units(item.balance_minor, item.account.currency):>18}"
        )


def _print_transactions(transactions) -> None:
    if not transactions:
        print("No transactions.")
        return
    print(f"{'DATE':<10} {'KIND':<15} {'AMOUNT':>16} {'DESCRIPTION':<32} ID")
    for item in transactions:
        print(
            f"{item.occurred_on:<10} {item.kind:<15} "
            f"{format_minor_units(item.amount_minor, item.currency):>16} "
            f"{item.description[:32]:<32} {item.id}"
        )


def _print_recorded(service: LedgerService, transaction_id: str) -> None:
    transaction = service.transaction(transaction_id)
    print(
        f"Posted {transaction.kind}: "
        f"{format_minor_units(transaction.amount_minor, transaction.currency)} "
        f"[{transaction.id}]"
    )


def _print_transaction(transaction) -> None:
    print(json.dumps(asdict(transaction), ensure_ascii=False, indent=2, sort_keys=True))


def _print_inbox_messages(messages) -> None:
    if not messages:
        print("No inbox messages.")
        return
    print(f"{'STATUS':<10} {'CHANNEL':<14} {'CONFIDENCE':<10} {'CONTENT':<40} ID")
    for message in messages:
        confidence = message.confidence or "-"
        content = message.content.replace("\n", " ")[:40]
        print(
            f"{message.status:<10} {message.channel:<14} {confidence:<10} "
            f"{content:<40} {message.id}"
        )


def _print_proposal(proposal) -> None:
    missing = ",".join(proposal.missing_fields) or "none"
    print(
        f"Proposal {proposal.id}: kind={proposal.kind} "
        f"confidence={proposal.confidence:.2f} missing={missing}"
    )
    print(json.dumps(proposal.payload, ensure_ascii=False, sort_keys=True))


def _doctor(database: str | Path) -> dict[str, object]:
    db.check_integrity(database)
    connection = db.connect(database)
    try:
        unbalanced = connection.execute(
            """
            SELECT count(*) FROM (
                SELECT t.id
                FROM transactions t JOIN postings p ON p.transaction_id = t.id
                WHERE t.status = 'posted'
                GROUP BY t.id HAVING sum(p.amount_minor) != 0 OR count(*) < 2
            )
            """
        ).fetchone()[0]
        if unbalanced:
            raise ValidationError(f"database contains {unbalanced} unbalanced transaction(s)")
        currency_mismatches = connection.execute(
            """
            SELECT count(*)
            FROM posted_postings p
            JOIN transactions t ON t.id = p.transaction_id
            JOIN accounts a ON a.id = p.account_id
            WHERE t.currency != a.currency
            """
        ).fetchone()[0]
        if currency_mismatches:
            raise ValidationError(
                f"database contains {currency_mismatches} posting currency mismatch(es)"
            )
        invalid_reversals = connection.execute(
            """
            SELECT count(*)
            FROM transactions original
            LEFT JOIN transactions reversal ON reversal.id = original.reversed_by_id
            LEFT JOIN transaction_links link
                ON link.from_transaction_id = reversal.id
                AND link.to_transaction_id = original.id
                AND link.relation = 'reversal_of'
            WHERE original.reversed_by_id IS NOT NULL
                AND (reversal.kind != 'reversal' OR reversal.status != 'posted'
                    OR link.from_transaction_id IS NULL)
            """
        ).fetchone()[0]
        if invalid_reversals:
            raise ValidationError(
                f"database contains {invalid_reversals} invalid reversal marker(s)"
            )
        inbox_inconsistencies = connection.execute(
            """
            SELECT count(*) FROM (
                SELECT m.id
                FROM raw_messages m
                WHERE m.status = 'proposed' AND NOT EXISTS (
                    SELECT 1 FROM transaction_proposals p
                    WHERE p.raw_message_id = m.id AND p.status = 'proposed'
                )
                UNION ALL
                SELECT m.id
                FROM raw_messages m
                WHERE m.status = 'confirmed' AND NOT EXISTS (
                    SELECT 1 FROM transaction_proposals p
                    WHERE p.raw_message_id = m.id AND p.status = 'confirmed'
                )
                UNION ALL
                SELECT m.id
                FROM raw_messages m
                WHERE m.status = 'rejected' AND NOT EXISTS (
                    SELECT 1 FROM transaction_proposals p
                    WHERE p.raw_message_id = m.id AND p.status = 'rejected'
                )
            )
            """
        ).fetchone()[0]
        if inbox_inconsistencies:
            raise ValidationError(
                f"database contains {inbox_inconsistencies} inbox state inconsistency(ies)"
            )
        posted = connection.execute(
            "SELECT count(*) FROM transactions WHERE status = 'posted'"
        ).fetchone()[0]
        drafts = connection.execute(
            "SELECT count(*) FROM transactions WHERE status = 'draft'"
        ).fetchone()[0]
        inbox_messages = connection.execute("SELECT count(*) FROM raw_messages").fetchone()[0]
        open_proposals = connection.execute(
            "SELECT count(*) FROM transaction_proposals WHERE status = 'proposed'"
        ).fetchone()[0]
        return {
            "database": str(Path(database)),
            "schema_version": db.current_schema_version(connection),
            "posted_transactions": int(posted),
            "draft_transactions": int(drafts),
            "unbalanced_transactions": int(unbalanced),
            "currency_mismatches": int(currency_mismatches),
            "invalid_reversal_markers": int(invalid_reversals),
            "inbox_messages": int(inbox_messages),
            "open_proposals": int(open_proposals),
            "inbox_inconsistencies": int(inbox_inconsistencies),
            "integrity": "ok",
        }
    finally:
        connection.close()
