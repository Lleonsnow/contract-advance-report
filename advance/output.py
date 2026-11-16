import csv
from pathlib import Path

from advance.allocation import Report
from advance.money import format_rub, format_rub_csv

_STATUS_RU = {
    "done": "выполнена",
    "planned": "запланирована",
    "cancelled": "отменена",
}

_WORK_MONEY_COLS = frozenset({4, 5, 6, 7, 8, 9})
_CONTRACT_MONEY_COLS = frozenset({2, 3, 4, 5, 6, 7, 8, 9})
_PAYMENT_MONEY_COLS = frozenset({3})


def status_ru(status: str) -> str:
    return _STATUS_RU.get(status, status)


def print_report(report: Report) -> None:
    print(f"Отчёт на дату {report.as_of.strftime('%d.%m.%Y')}")
    print()
    print("Работы")
    work_headers = (
        "Договор",
        "Работа",
        "Название",
        "Статус",
        "Цена",
        "Привязано",
        "Из аванса",
        "Выплачено",
        "Осталось",
        "Перенесено в пул",
    )
    work_rows = [
        (
            r.contract_id,
            r.work_id,
            r.title,
            status_ru(r.status_on_d),
            format_rub(r.price_kopecks),
            format_rub(r.paid_bound_kopecks),
            format_rub(r.paid_from_pool_kopecks),
            format_rub(r.paid_total_kopecks),
            format_rub(r.remaining_kopecks),
            format_rub(r.redirected_to_pool_kopecks),
        )
        for r in report.work_rows
    ]
    _print_table(work_headers, work_rows, _WORK_MONEY_COLS)

    print()
    print("Договоры")
    contract_headers = (
        "Договор",
        "Подрядчик",
        "Сумма",
        "К оплате",
        "Выплачено",
        "Распределено",
        "Аванс под невыполненные",
        "Переплата",
        "Перенесено в пул",
        "Осталось",
    )
    contract_rows = [
        (
            r.contract_id,
            r.contractor,
            format_rub(r.amount_kopecks),
            format_rub(r.payable_kopecks),
            format_rub(r.paid_kopecks),
            format_rub(r.allocated_to_works_kopecks),
            format_rub(r.advance_for_planned_kopecks),
            format_rub(r.overpayment_kopecks),
            format_rub(r.redirected_to_pool_kopecks),
            format_rub(r.remaining_kopecks),
        )
        for r in report.contract_rows
    ]
    _print_table(contract_headers, contract_rows, _CONTRACT_MONEY_COLS)

    print()
    print("Платежи")
    payment_headers = (
        "Платёж",
        "Договор",
        "Назначение",
        "Сумма",
        "Статус на дату",
        "Куда пошёл",
    )
    payment_rows = [
        (
            r.payment_id,
            r.contract_id,
            r.purpose,
            format_rub(r.amount_kopecks),
            r.status_on_d,
            r.destination,
        )
        for r in report.payment_rows
    ]
    _print_table(payment_headers, payment_rows, _PAYMENT_MONEY_COLS)


def _print_table(
    headers: tuple[str, ...],
    rows: list[tuple[str, ...]],
    money_cols: frozenset[int],
) -> None:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    header_line = "  ".join(
        h.rjust(widths[i]) if i in money_cols else h.ljust(widths[i]) for i, h in enumerate(headers)
    )
    print(header_line)
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print(
            "  ".join(
                cell.rjust(widths[i]) if i in money_cols else cell.ljust(widths[i])
                for i, cell in enumerate(row)
            )
        )


def write_csv(report: Report, path: Path) -> None:
    headers = [
        "Раздел",
        "Договор",
        "Подрядчик",
        "Работа",
        "Название",
        "Статус",
        "Сумма договора",
        "К оплате",
        "Цена",
        "Привязано",
        "Из аванса",
        "Выплачено",
        "Распределено",
        "Аванс под невыполненные",
        "Переплата",
        "Перенесено в пул",
        "Осталось",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow(headers)
        for r in report.work_rows:
            writer.writerow(
                [
                    "работа",
                    r.contract_id,
                    "",
                    r.work_id,
                    r.title,
                    status_ru(r.status_on_d),
                    "",
                    "",
                    format_rub_csv(r.price_kopecks),
                    format_rub_csv(r.paid_bound_kopecks),
                    format_rub_csv(r.paid_from_pool_kopecks),
                    format_rub_csv(r.paid_total_kopecks),
                    "",
                    "",
                    "",
                    format_rub_csv(r.redirected_to_pool_kopecks),
                    format_rub_csv(r.remaining_kopecks),
                ]
            )
        for r in report.contract_rows:
            writer.writerow(
                [
                    "договор",
                    r.contract_id,
                    r.contractor,
                    "",
                    "",
                    "",
                    format_rub_csv(r.amount_kopecks),
                    format_rub_csv(r.payable_kopecks),
                    "",
                    "",
                    "",
                    format_rub_csv(r.paid_kopecks),
                    format_rub_csv(r.allocated_to_works_kopecks),
                    format_rub_csv(r.advance_for_planned_kopecks),
                    format_rub_csv(r.overpayment_kopecks),
                    format_rub_csv(r.redirected_to_pool_kopecks),
                    format_rub_csv(r.remaining_kopecks),
                ]
            )


def write_payments_csv(report: Report, path: Path) -> None:
    headers = [
        "Платёж",
        "Договор",
        "Назначение",
        "Сумма",
        "Статус на дату",
        "Куда пошёл",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow(headers)
        for r in report.payment_rows:
            writer.writerow(
                [
                    r.payment_id,
                    r.contract_id,
                    r.purpose,
                    format_rub_csv(r.amount_kopecks),
                    r.status_on_d,
                    r.destination,
                ]
            )
