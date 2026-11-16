import unittest
from datetime import date
from pathlib import Path

from advance.allocation import allocate
from advance.loader import load_data

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RUB = 100


class TestPaymentRows(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = load_data(DATA_DIR)
        cls.report = allocate(cls.dataset, date(2026, 11, 10))
        cls.by_id = {r.payment_id: r for r in cls.report.payment_rows}
        cls.contracts = {r.contract_id: r for r in cls.report.contract_rows}

    def test_statuses_on_2026_11_10(self) -> None:
        for pid in ("P-1", "P-3", "P-5", "P-6", "P-7"):
            self.assertEqual(self.by_id[pid].status_on_d, "учтён", pid)
        self.assertEqual(self.by_id["P-2"].status_on_d, "возвращён до даты")
        self.assertEqual(self.by_id["P-4"].status_on_d, "в очереди")
        self.assertEqual(self.by_id["P-8"].status_on_d, "оплачен после даты")

    def test_destinations(self) -> None:
        self.assertEqual(self.by_id["P-1"].destination, "аванс договора")
        self.assertEqual(self.by_id["P-3"].destination, "W-14")
        self.assertEqual(self.by_id["P-2"].destination, "—")
        self.assertEqual(self.by_id["P-4"].destination, "—")
        self.assertEqual(self.by_id["P-8"].destination, "—")

    def test_counted_sum_equals_paid_kopecks(self) -> None:
        for contract_id, contract_row in self.contracts.items():
            counted = sum(
                r.amount_kopecks
                for r in self.report.payment_rows
                if r.contract_id == contract_id and r.status_on_d == "учтён"
            )
            self.assertEqual(counted, contract_row.paid_kopecks, contract_id)


if __name__ == "__main__":
    unittest.main()
