import csv
from datetime import date
from pathlib import Path

from advance.allocation import work_status_on
from advance.models import Contract, Dataset, Payment, Work
from advance.money import format_rub, parse_kopecks

WORK_STATUSES = frozenset({"planned", "done", "cancelled"})
PAYMENT_STATUSES = frozenset({"paid", "queued", "refunded"})


def _parse_date(raw: str, *, source: str, line_no: int, field: str) -> date | None:
    value = raw.strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Некорректная дата {field}={raw!r} в {source}, строка {line_no}") from exc


def _require_date(
    value: date | None,
    *,
    source: str,
    line_no: int,
    field: str,
    context: str,
) -> date:
    if value is None:
        raise ValueError(f"{context}: требуется {field} в {source}, строка {line_no}")
    return value


def _require_empty(
    value: date | None,
    *,
    source: str,
    line_no: int,
    field: str,
    context: str,
) -> None:
    if value is not None:
        raise ValueError(f"{context}: поле {field} должно быть пустым в {source}, строка {line_no}")


def _load_contracts(path: Path) -> tuple[Contract, ...]:
    source = str(path)
    contracts: list[Contract] = []
    seen: set[str] = set()
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for line_no, row in enumerate(reader, start=2):
            contract_id = row["contract_id"].strip()
            if contract_id in seen:
                raise ValueError(f"Дубликат contract_id={contract_id!r} в {source}")
            seen.add(contract_id)
            signed_at = _require_date(
                _parse_date(row["signed_at"], source=source, line_no=line_no, field="signed_at"),
                source=source,
                line_no=line_no,
                field="signed_at",
                context=f"Договор {contract_id}",
            )
            contracts.append(
                Contract(
                    contract_id=contract_id,
                    contractor=row["contractor"],
                    amount_kopecks=parse_kopecks(row["amount"], source=source, line_no=line_no),
                    signed_at=signed_at,
                )
            )
    return tuple(contracts)


def _load_works(path: Path, contract_ids: set[str]) -> tuple[Work, ...]:
    source = str(path)
    works: list[Work] = []
    seen: set[str] = set()
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for line_no, row in enumerate(reader, start=2):
            work_id = row["work_id"].strip()
            if work_id in seen:
                raise ValueError(f"Дубликат work_id={work_id!r} в {source}")
            seen.add(work_id)
            contract_id = row["contract_id"].strip()
            if contract_id not in contract_ids:
                raise ValueError(
                    f"Работа {work_id}: неизвестный contract_id={contract_id!r} "
                    f"в {source}, строка {line_no}"
                )
            status = row["status"].strip()
            if status not in WORK_STATUSES:
                raise ValueError(
                    f"Работа {work_id}: недопустимый status={status!r} в {source}, строка {line_no}"
                )
            completed_at = _parse_date(
                row["completed_at"], source=source, line_no=line_no, field="completed_at"
            )
            cancelled_at = _parse_date(
                row["cancelled_at"], source=source, line_no=line_no, field="cancelled_at"
            )
            context = f"Работа {work_id} со статусом {status}"
            if status == "planned":
                _require_empty(
                    completed_at,
                    source=source,
                    line_no=line_no,
                    field="completed_at",
                    context=context,
                )
                _require_empty(
                    cancelled_at,
                    source=source,
                    line_no=line_no,
                    field="cancelled_at",
                    context=context,
                )
            if status == "done":
                _require_date(
                    completed_at,
                    source=source,
                    line_no=line_no,
                    field="completed_at",
                    context=context,
                )
                _require_empty(
                    cancelled_at,
                    source=source,
                    line_no=line_no,
                    field="cancelled_at",
                    context=context,
                )
            if status == "cancelled":
                _require_date(
                    cancelled_at,
                    source=source,
                    line_no=line_no,
                    field="cancelled_at",
                    context=context,
                )
            price = parse_kopecks(row["price"], source=source, line_no=line_no)
            if price <= 0:
                raise ValueError(
                    f"Работа {work_id}: цена должна быть > 0 в {source}, строка {line_no}"
                )
            works.append(
                Work(
                    work_id=work_id,
                    contract_id=contract_id,
                    title=row["title"],
                    price_kopecks=price,
                    status=status,
                    completed_at=completed_at,
                    cancelled_at=cancelled_at,
                )
            )
    return tuple(works)


def _check_date_order(
    *,
    created_at: date,
    paid_at: date | None,
    refunded_at: date | None,
    source: str,
    line_no: int,
    payment_id: str,
) -> None:
    if paid_at is not None and created_at > paid_at:
        raise ValueError(f"Платёж {payment_id}: created_at > paid_at в {source}, строка {line_no}")
    if refunded_at is not None and paid_at is not None and paid_at > refunded_at:
        raise ValueError(f"Платёж {payment_id}: paid_at > refunded_at в {source}, строка {line_no}")
    if refunded_at is not None and paid_at is None and created_at > refunded_at:
        raise ValueError(
            f"Платёж {payment_id}: created_at > refunded_at в {source}, строка {line_no}"
        )


def _load_payments(
    path: Path,
    contract_ids: set[str],
    works_by_id: dict[str, Work],
) -> tuple[Payment, ...]:
    source = str(path)
    payments: list[Payment] = []
    seen: set[str] = set()
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for line_no, row in enumerate(reader, start=2):
            payment_id = row["payment_id"].strip()
            if payment_id in seen:
                raise ValueError(f"Дубликат payment_id={payment_id!r} в {source}")
            seen.add(payment_id)
            contract_id = row["contract_id"].strip()
            if contract_id not in contract_ids:
                raise ValueError(
                    f"Платёж {payment_id}: неизвестный contract_id={contract_id!r} "
                    f"в {source}, строка {line_no}"
                )
            work_raw = row["work_id"].strip()
            work_id = work_raw or None
            if work_id is not None:
                work = works_by_id.get(work_id)
                if work is None:
                    raise ValueError(
                        f"Платёж {payment_id}: неизвестный work_id={work_id!r} "
                        f"в {source}, строка {line_no}"
                    )
                if work.contract_id != contract_id:
                    raise ValueError(
                        f"Платёж {payment_id}: work_id={work_id!r} относится к "
                        f"{work.contract_id}, а не к {contract_id} "
                        f"в {source}, строка {line_no}"
                    )
            status = row["status"].strip()
            if status not in PAYMENT_STATUSES:
                raise ValueError(
                    f"Платёж {payment_id}: недопустимый status={status!r} "
                    f"в {source}, строка {line_no}"
                )
            created_at = _require_date(
                _parse_date(row["created_at"], source=source, line_no=line_no, field="created_at"),
                source=source,
                line_no=line_no,
                field="created_at",
                context=f"Платёж {payment_id}",
            )
            paid_at = _parse_date(row["paid_at"], source=source, line_no=line_no, field="paid_at")
            refunded_at = _parse_date(
                row["refunded_at"], source=source, line_no=line_no, field="refunded_at"
            )
            context = f"Платёж {payment_id} со статусом {status}"
            if status == "queued":
                _require_empty(
                    paid_at,
                    source=source,
                    line_no=line_no,
                    field="paid_at",
                    context=context,
                )
                _require_empty(
                    refunded_at,
                    source=source,
                    line_no=line_no,
                    field="refunded_at",
                    context=context,
                )
            if status == "paid":
                _require_date(
                    paid_at,
                    source=source,
                    line_no=line_no,
                    field="paid_at",
                    context=context,
                )
                _require_empty(
                    refunded_at,
                    source=source,
                    line_no=line_no,
                    field="refunded_at",
                    context=context,
                )
            if status == "refunded":
                _require_date(
                    paid_at,
                    source=source,
                    line_no=line_no,
                    field="paid_at",
                    context=context,
                )
                _require_date(
                    refunded_at,
                    source=source,
                    line_no=line_no,
                    field="refunded_at",
                    context=context,
                )
            _check_date_order(
                created_at=created_at,
                paid_at=paid_at,
                refunded_at=refunded_at,
                source=source,
                line_no=line_no,
                payment_id=payment_id,
            )
            amount = parse_kopecks(row["amount"], source=source, line_no=line_no)
            if amount <= 0:
                raise ValueError(
                    f"Платёж {payment_id}: сумма должна быть > 0 в {source}, строка {line_no}"
                )
            payments.append(
                Payment(
                    payment_id=payment_id,
                    contract_id=contract_id,
                    work_id=work_id,
                    purpose=row["purpose"],
                    amount_kopecks=amount,
                    status=status,
                    created_at=created_at,
                    paid_at=paid_at,
                    refunded_at=refunded_at,
                )
            )
    return tuple(payments)


def load_data(data_dir: Path) -> Dataset:
    contracts = _load_contracts(data_dir / "contracts.csv")
    contract_ids = {c.contract_id for c in contracts}
    works = _load_works(data_dir / "works.csv", contract_ids)
    works_by_id = {w.work_id: w for w in works}
    payments = _load_payments(data_dir / "payments.csv", contract_ids, works_by_id)
    return Dataset(contracts=contracts, works=works, payments=payments)


def check_warnings(dataset: Dataset, as_of: date) -> list[str]:
    warnings: list[str] = []
    contracts = {c.contract_id: c for c in dataset.contracts}
    works_by_contract: dict[str, list[Work]] = {c.contract_id: [] for c in dataset.contracts}
    for work in dataset.works:
        works_by_contract.setdefault(work.contract_id, []).append(work)

    for contract in dataset.contracts:
        works = works_by_contract.get(contract.contract_id, [])
        all_prices = sum(w.price_kopecks for w in works)
        if all_prices != contract.amount_kopecks:
            warnings.append(
                f"Договор {contract.contract_id}: сумма договора "
                f"{format_rub(contract.amount_kopecks)} ≠ сумма цен всех работ "
                f"{format_rub(all_prices)}"
            )
        active_prices = sum(
            w.price_kopecks for w in works if work_status_on(w, as_of) != "cancelled"
        )
        if active_prices != contract.amount_kopecks:
            warnings.append(
                f"Договор {contract.contract_id} на {as_of.strftime('%d.%m.%Y')}: "
                f"сумма договора {format_rub(contract.amount_kopecks)} ≠ "
                f"сумма цен неотменённых работ {format_rub(active_prices)}"
            )

    for work in dataset.works:
        contract = contracts[work.contract_id]
        for field, value in (
            ("completed_at", work.completed_at),
            ("cancelled_at", work.cancelled_at),
        ):
            if value is not None and value < contract.signed_at:
                warnings.append(
                    f"Работа {work.work_id}: {field}={value.isoformat()} раньше "
                    f"подписания договора {contract.signed_at.isoformat()}"
                )

    for payment in dataset.payments:
        contract = contracts[payment.contract_id]
        for field, value in (
            ("created_at", payment.created_at),
            ("paid_at", payment.paid_at),
        ):
            if value is not None and value < contract.signed_at:
                warnings.append(
                    f"Платёж {payment.payment_id}: {field}={value.isoformat()} раньше "
                    f"подписания договора {contract.signed_at.isoformat()}"
                )

    dates: list[date] = []
    for contract in dataset.contracts:
        dates.append(contract.signed_at)
    for work in dataset.works:
        if work.completed_at is not None:
            dates.append(work.completed_at)
        if work.cancelled_at is not None:
            dates.append(work.cancelled_at)
    for payment in dataset.payments:
        dates.append(payment.created_at)
        if payment.paid_at is not None:
            dates.append(payment.paid_at)
        if payment.refunded_at is not None:
            dates.append(payment.refunded_at)
    if dates:
        max_date = max(dates)
        if as_of > max_date:
            warnings.append(
                f"Дата отчёта {as_of.strftime('%d.%m.%Y')} позже самой поздней даты "
                f"в данных ({max_date.strftime('%d.%m.%Y')}). Статусы в выгрузке даны "
                f"на момент выгрузки; после неё могли быть события, которых в данных нет."
            )

    return warnings
