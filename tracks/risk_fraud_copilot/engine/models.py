"""Shared data loading + dataclasses for customers, accounts, transactions."""
import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).parent.parent / "data"


@dataclass
class Customer:
    customer_id: str
    name: str
    type: str
    risk_rating: str
    country: str
    occupation_or_industry: str
    onboarding_date: str


@dataclass
class Account:
    account_id: str
    customer_id: str
    account_type: str
    opened_date: str
    status: str
    currency: str
    vpa: str = ""  # UPI Virtual Payment Address linked to this account, if any (India UPI rail)


@dataclass
class Transaction:
    txn_id: str
    account_id: str
    customer_id: str
    timestamp: datetime
    amount: float
    currency: str
    type: str
    counterparty_name: str
    counterparty_country: str
    channel: str
    location: str
    description: str


def load_customers() -> dict[str, Customer]:
    out = {}
    with (DATA_DIR / "customers.csv").open() as f:
        for row in csv.DictReader(f):
            out[row["customer_id"]] = Customer(**row)
    return out


def load_accounts() -> dict[str, Account]:
    out = {}
    with (DATA_DIR / "accounts.csv").open() as f:
        for row in csv.DictReader(f):
            out[row["account_id"]] = Account(**row)
    return out


def load_transactions() -> list[Transaction]:
    out = []
    with (DATA_DIR / "transactions.csv").open() as f:
        for row in csv.DictReader(f):
            row["timestamp"] = datetime.fromisoformat(row["timestamp"])
            row["amount"] = float(row["amount"])
            out.append(Transaction(**row))
    out.sort(key=lambda t: t.timestamp)
    return out


class DataStore:
    """Loads once, indexes by account/customer for fast lookups."""

    def __init__(self):
        self.customers = load_customers()
        self.accounts = load_accounts()
        self.transactions = load_transactions()
        self.txn_by_id = {t.txn_id: t for t in self.transactions}
        self.txns_by_account: dict[str, list[Transaction]] = {}
        for t in self.transactions:
            self.txns_by_account.setdefault(t.account_id, []).append(t)
        for lst in self.txns_by_account.values():
            lst.sort(key=lambda t: t.timestamp)
        self.account_by_vpa: dict[str, str] = {
            a.vpa: a.account_id for a in self.accounts.values() if a.vpa
        }

    def account_transactions(self, account_id: str) -> list[Transaction]:
        return self.txns_by_account.get(account_id, [])

    def account_id_for_vpa(self, vpa: str) -> Optional[str]:
        return self.account_by_vpa.get(vpa)

    def customer_accounts(self, customer_id: str) -> list[Account]:
        return [a for a in self.accounts.values() if a.customer_id == customer_id]
