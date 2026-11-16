from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Contract:
    contract_id: str
    contractor: str
    amount_kopecks: int
    signed_at: date


@dataclass(frozen=True)
class Work:
    work_id: str
    contract_id: str
    title: str
    price_kopecks: int
    status: str
    completed_at: date | None
    cancelled_at: date | None


@dataclass(frozen=True)
class Payment:
    payment_id: str
    contract_id: str
    work_id: str | None
    purpose: str
    amount_kopecks: int
    status: str
    created_at: date
    paid_at: date | None
    refunded_at: date | None


@dataclass(frozen=True)
class Dataset:
    contracts: tuple[Contract, ...]
    works: tuple[Work, ...]
    payments: tuple[Payment, ...]
