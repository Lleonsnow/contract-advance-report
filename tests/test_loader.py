import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from advance.loader import check_warnings, load_data

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

CONTRACTS_HEADER = ["contract_id", "contractor", "amount", "signed_at"]
WORKS_HEADER = [
    "work_id",
    "contract_id",
    "title",
    "price",
    "status",
    "completed_at",
    "cancelled_at",
]
PAYMENTS_HEADER = [
    "payment_id",
    "contract_id",
    "work_id",
    "purpose",
    "amount",
    "status",
    "created_at",
    "paid_at",
    "refunded_at",
]


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


def _base_ok(tmp: Path) -> None:
    _write_csv(
        tmp / "contracts.csv",
        CONTRACTS_HEADER,
        [["C-1", "X", "100.00", "2026-01-01"]],
    )
    _write_csv(
        tmp / "works.csv",
        WORKS_HEADER,
        [["W-1", "C-1", "Work", "100.00", "done", "2026-02-01", ""]],
    )
    _write_csv(
        tmp / "payments.csv",
        PAYMENTS_HEADER,
        [["P-1", "C-1", "", "Adv", "50.00", "paid", "2026-01-10", "2026-01-15", ""]],
    )


class TestLoaderErrors(unittest.TestCase):
    def _load_variant(self, *, works=None, payments=None, contracts=None) -> None:
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            _base_ok(tmp)
            if contracts is not None:
                _write_csv(tmp / "contracts.csv", CONTRACTS_HEADER, contracts)
            if works is not None:
                _write_csv(tmp / "works.csv", WORKS_HEADER, works)
            if payments is not None:
                _write_csv(tmp / "payments.csv", PAYMENTS_HEADER, payments)
            load_data(tmp)

    def test_invalid_amount(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            self._load_variant(
                payments=[["P-1", "C-1", "", "Adv", "50", "paid", "2026-01-10", "2026-01-15", ""]]
            )
        message = str(ctx.exception)
        self.assertIn("строка 2", message)
        self.assertIn("payments.csv", message)

    def test_unknown_work_status(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            self._load_variant(
                works=[["W-1", "C-1", "Work", "100.00", "archived", "2026-02-01", ""]]
            )
        message = str(ctx.exception)
        self.assertIn("строка 2", message)
        self.assertIn("status", message)

    def test_work_id_foreign_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            _write_csv(
                tmp / "contracts.csv",
                CONTRACTS_HEADER,
                [
                    ["C-1", "X", "100.00", "2026-01-01"],
                    ["C-2", "Y", "100.00", "2026-01-01"],
                ],
            )
            _write_csv(
                tmp / "works.csv",
                WORKS_HEADER,
                [
                    ["W-1", "C-1", "Work", "100.00", "done", "2026-02-01", ""],
                    ["W-2", "C-2", "Work2", "100.00", "done", "2026-02-01", ""],
                ],
            )
            _write_csv(
                tmp / "payments.csv",
                PAYMENTS_HEADER,
                [
                    [
                        "P-1",
                        "C-1",
                        "W-2",
                        "Adv",
                        "50.00",
                        "paid",
                        "2026-01-10",
                        "2026-01-15",
                        "",
                    ]
                ],
            )
            with self.assertRaises(ValueError) as ctx:
                load_data(tmp)
            message = str(ctx.exception)
            self.assertIn("строка 2", message)
            self.assertIn("W-2", message)

    def test_queued_with_paid_at(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            self._load_variant(
                payments=[
                    [
                        "P-1",
                        "C-1",
                        "",
                        "Adv",
                        "50.00",
                        "queued",
                        "2026-01-10",
                        "2026-01-15",
                        "",
                    ]
                ]
            )
        message = str(ctx.exception)
        self.assertIn("строка 2", message)
        self.assertIn("paid_at", message)

    def test_refunded_at_before_paid_at(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            self._load_variant(
                payments=[
                    [
                        "P-1",
                        "C-1",
                        "",
                        "Adv",
                        "50.00",
                        "refunded",
                        "2026-01-10",
                        "2026-01-20",
                        "2026-01-15",
                    ]
                ]
            )
        message = str(ctx.exception)
        self.assertIn("строка 2", message)
        self.assertIn("paid_at", message)


class TestLoaderWarnings(unittest.TestCase):
    def test_d1_amount_mismatch_warning(self) -> None:
        dataset = load_data(DATA_DIR)
        warnings = check_warnings(dataset, date(2026, 11, 10))
        joined = "\n".join(warnings)
        self.assertIn("D-1", joined)
        self.assertIn("600 000,00", joined)
        self.assertIn("500 000,00", joined)

    def test_as_of_after_latest_data_date(self) -> None:
        dataset = load_data(DATA_DIR)
        warnings = check_warnings(dataset, date(2026, 12, 1))
        joined = "\n".join(warnings)
        self.assertIn("позже самой поздней даты", joined)
        self.assertIn("12.11.2026", joined)


if __name__ == "__main__":
    unittest.main()
