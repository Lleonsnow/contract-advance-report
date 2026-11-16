from dataclasses import dataclass
from datetime import date

from advance.models import Contract, Dataset, Payment, Work


@dataclass(frozen=True)
class WorkView:
    work: Work
    status_on_d: str


@dataclass(frozen=True)
class WorkRow:
    contract_id: str
    work_id: str
    title: str
    status_on_d: str
    price_kopecks: int
    paid_bound_kopecks: int
    paid_from_pool_kopecks: int
    paid_total_kopecks: int
    remaining_kopecks: int
    redirected_to_pool_kopecks: int


@dataclass(frozen=True)
class ContractRow:
    contract_id: str
    contractor: str
    amount_kopecks: int
    payable_kopecks: int
    paid_kopecks: int
    allocated_to_works_kopecks: int
    advance_for_planned_kopecks: int
    overpayment_kopecks: int
    redirected_to_pool_kopecks: int
    remaining_kopecks: int


@dataclass(frozen=True)
class PaymentRow:
    payment_id: str
    contract_id: str
    purpose: str
    amount_kopecks: int
    status_on_d: str
    destination: str


@dataclass(frozen=True)
class Report:
    as_of: date
    work_rows: tuple[WorkRow, ...]
    contract_rows: tuple[ContractRow, ...]
    payment_rows: tuple[PaymentRow, ...]


def payment_counts(payment: Payment, as_of: date) -> bool:
    if payment.paid_at is None or payment.paid_at > as_of:
        return False
    if (
        payment.status == "refunded"
        and payment.refunded_at is not None
        and payment.refunded_at <= as_of
    ):
        return False
    return True


def work_status_on(work: Work, as_of: date) -> str:
    if work.cancelled_at is not None and work.cancelled_at <= as_of:
        return "cancelled"
    if work.completed_at is not None and work.completed_at <= as_of:
        return "done"
    return "planned"


def payment_status_on(payment: Payment, as_of: date) -> str:
    if payment.status == "queued":
        return "в очереди"
    if (
        payment.status == "refunded"
        and payment.refunded_at is not None
        and payment.refunded_at <= as_of
    ):
        return "возвращён до даты"
    if payment.paid_at is None or payment.paid_at > as_of:
        return "оплачен после даты"
    return "учтён"


def _bound_destination(
    payment: Payment,
    as_of: date,
    works_by_id: dict[str, Work],
    applied_so_far: dict[str, int],
) -> str:
    assert payment.work_id is not None
    work = works_by_id[payment.work_id]
    if work_status_on(work, as_of) == "cancelled":
        return f"перенесён в пул (работа {payment.work_id} отменена)"
    already = applied_so_far.get(payment.work_id, 0)
    room = work.price_kopecks - already
    if room <= 0:
        return "перенесён в пул (оплата сверх цены)"
    if payment.amount_kopecks <= room:
        applied_so_far[payment.work_id] = already + payment.amount_kopecks
        return payment.work_id
    applied_so_far[payment.work_id] = work.price_kopecks
    return f"{payment.work_id}; перенесён в пул (оплата сверх цены)"


def build_payment_rows(
    payments: tuple[Payment, ...] | list[Payment],
    works_by_id: dict[str, Work],
    as_of: date,
) -> list[PaymentRow]:
    applied_so_far: dict[str, int] = {}
    rows: list[PaymentRow] = []
    for payment in payments:
        status = payment_status_on(payment, as_of)
        if status != "учтён":
            destination = "—"
        elif payment.work_id is None:
            destination = "аванс договора"
        else:
            destination = _bound_destination(payment, as_of, works_by_id, applied_so_far)
        rows.append(
            PaymentRow(
                payment_id=payment.payment_id,
                contract_id=payment.contract_id,
                purpose=payment.purpose,
                amount_kopecks=payment.amount_kopecks,
                status_on_d=status,
                destination=destination,
            )
        )
    return rows


def order_works_for_pool(works: list[WorkView]) -> list[WorkView]:
    done = sorted(
        (w for w in works if w.status_on_d == "done"),
        key=lambda w: (w.work.completed_at, w.work.work_id),
    )
    planned = sorted(
        (w for w in works if w.status_on_d == "planned"),
        key=lambda w: w.work.work_id,
    )
    return [*done, *planned]


def distribute_pool(
    pool: int,
    ordered: list[WorkView],
    already: dict[str, int],
) -> dict[str, int]:
    from_pool: dict[str, int] = {}
    remaining_pool = pool
    for view in ordered:
        work_id = view.work.work_id
        need = view.work.price_kopecks - already.get(work_id, 0)
        if need <= 0 or remaining_pool <= 0:
            from_pool[work_id] = 0
            continue
        take = min(need, remaining_pool)
        from_pool[work_id] = take
        remaining_pool -= take
    return from_pool


def allocate_contract(
    contract: Contract,
    works: list[Work],
    payments: list[Payment],
    as_of: date,
) -> tuple[list[WorkRow], ContractRow]:
    views = [WorkView(work=w, status_on_d=work_status_on(w, as_of)) for w in works]

    counted = [p for p in payments if payment_counts(p, as_of)]
    paid_total = sum(p.amount_kopecks for p in counted)

    bound_raw: dict[str, int] = {v.work.work_id: 0 for v in views}
    pool = 0
    for payment in counted:
        if payment.work_id is None:
            pool += payment.amount_kopecks
        else:
            bound_raw[payment.work_id] = bound_raw.get(payment.work_id, 0) + payment.amount_kopecks

    bound_applied: dict[str, int] = {}
    redirected: dict[str, int] = {v.work.work_id: 0 for v in views}

    for view in views:
        work_id = view.work.work_id
        raw = bound_raw.get(work_id, 0)
        if view.status_on_d == "cancelled":
            bound_applied[work_id] = 0
            redirected[work_id] = raw
            pool += raw
            continue
        applied = min(raw, view.work.price_kopecks)
        excess = raw - applied
        bound_applied[work_id] = applied
        redirected[work_id] = excess
        pool += excess

    active = [v for v in views if v.status_on_d != "cancelled"]
    ordered = order_works_for_pool(active)
    from_pool = distribute_pool(pool, ordered, bound_applied)
    allocated_from_pool = sum(from_pool.values())
    overpayment = pool - allocated_from_pool

    work_rows: list[WorkRow] = []
    for view in views:
        work = view.work
        work_id = work.work_id
        paid_bound = bound_applied.get(work_id, 0)
        paid_pool = from_pool.get(work_id, 0)
        paid_work = paid_bound + paid_pool
        if view.status_on_d == "cancelled":
            remaining = 0
        else:
            remaining = work.price_kopecks - paid_work
        work_rows.append(
            WorkRow(
                contract_id=contract.contract_id,
                work_id=work_id,
                title=work.title,
                status_on_d=view.status_on_d,
                price_kopecks=work.price_kopecks,
                paid_bound_kopecks=paid_bound,
                paid_from_pool_kopecks=paid_pool,
                paid_total_kopecks=paid_work,
                remaining_kopecks=remaining,
                redirected_to_pool_kopecks=redirected.get(work_id, 0),
            )
        )

    non_cancelled_rows = [r for r in work_rows if r.status_on_d != "cancelled"]
    payable = sum(r.price_kopecks for r in non_cancelled_rows)
    allocated_to_works = sum(r.paid_total_kopecks for r in non_cancelled_rows)
    advance_for_planned = sum(r.paid_total_kopecks for r in work_rows if r.status_on_d == "planned")
    remaining = sum(r.remaining_kopecks for r in non_cancelled_rows)
    redirected_total = sum(r.redirected_to_pool_kopecks for r in work_rows)

    contract_row = ContractRow(
        contract_id=contract.contract_id,
        contractor=contract.contractor,
        amount_kopecks=contract.amount_kopecks,
        payable_kopecks=payable,
        paid_kopecks=paid_total,
        allocated_to_works_kopecks=allocated_to_works,
        advance_for_planned_kopecks=advance_for_planned,
        overpayment_kopecks=overpayment,
        redirected_to_pool_kopecks=redirected_total,
        remaining_kopecks=remaining,
    )
    return work_rows, contract_row


def allocate(dataset: Dataset, as_of: date) -> Report:
    works_by_contract: dict[str, list[Work]] = {c.contract_id: [] for c in dataset.contracts}
    for work in dataset.works:
        works_by_contract.setdefault(work.contract_id, []).append(work)

    payments_by_contract: dict[str, list[Payment]] = {c.contract_id: [] for c in dataset.contracts}
    for payment in dataset.payments:
        payments_by_contract.setdefault(payment.contract_id, []).append(payment)

    all_work_rows: list[WorkRow] = []
    contract_rows: list[ContractRow] = []
    for contract in dataset.contracts:
        work_rows, contract_row = allocate_contract(
            contract,
            works_by_contract.get(contract.contract_id, []),
            payments_by_contract.get(contract.contract_id, []),
            as_of,
        )
        all_work_rows.extend(work_rows)
        contract_rows.append(contract_row)

    works_by_id = {w.work_id: w for w in dataset.works}
    payment_rows = build_payment_rows(dataset.payments, works_by_id, as_of)

    return Report(
        as_of=as_of,
        work_rows=tuple(all_work_rows),
        contract_rows=tuple(contract_rows),
        payment_rows=tuple(payment_rows),
    )
