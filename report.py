#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from advance.allocation import allocate
from advance.loader import check_warnings, load_data
from advance.output import print_report, write_csv, write_payments_csv


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Отчёт по авансам по договорам")
    parser.add_argument("--data", type=Path, required=True, help="Каталог с CSV")
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        required=True,
        help="Дата отчёта YYYY-MM-DD",
    )
    parser.add_argument("--csv", type=Path, default=None, help="Путь для CSV-выгрузки")
    return parser.parse_args(argv)


def _csv_inside_data(csv_path: Path, data_dir: Path) -> bool:
    data_resolved = data_dir.resolve()
    csv_resolved = csv_path.resolve()
    try:
        csv_resolved.relative_to(data_resolved)
    except ValueError:
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.csv is not None and _csv_inside_data(args.csv, args.data):
        print(
            f"Ошибка: путь --csv ({args.csv}) не должен находиться внутри --data ({args.data})",
            file=sys.stderr,
        )
        return 1
    try:
        dataset = load_data(args.data)
        report = allocate(dataset, args.date)
    except (OSError, ValueError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    print_report(report)
    warnings = check_warnings(dataset, args.date)
    if warnings:
        print("Предупреждения:", file=sys.stderr)
        for warning in warnings:
            print(f"- {warning}", file=sys.stderr)
    if args.csv is not None:
        write_csv(report, args.csv)
        payments_path = args.csv.with_name(f"{args.csv.stem}_payments.csv")
        write_payments_csv(report, payments_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
