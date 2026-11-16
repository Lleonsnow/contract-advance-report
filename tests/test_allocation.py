import unittest
from datetime import date
from pathlib import Path

from advance.allocation import (
    WorkView,
    allocate,
    distribute_pool,
    order_works_for_pool,
    payment_counts,
    work_status_on,
)
from advance.loader import load_data
from advance.models import Contract, Dataset, Payment, Work

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RUB = 100


def _work(
    work_id: str,
    contract_id: str = "C-1",
    price: int = 100 * RUB,
    *,
    completed_at: date | None = None,
    cancelled_at: date | None = None,
) -> Work:
    status = "planned"
    if cancelled_at is not None:
        status = "cancelled"
    elif completed_at is not None:
        status = "done"
    return Work(
        work_id=work_id,
        contract_id=contract_id,
        title=work_id,
        price_kopecks=price,
        status=status,
        completed_at=completed_at,
        cancelled_at=cancelled_at,
    )


def _payment(
    payment_id: str,
    amount: int,
    *,
    work_id: str | None = None,
    status: str = "paid",
    paid_at: date | None = date(2026, 9, 1),
    refunded_at: date | None = None,
    contract_id: str = "C-1",
    created_at: date = date(2026, 8, 1),
) -> Payment:
    return Payment(
        payment_id=payment_id,
        contract_id=contract_id,
        work_id=work_id,
        purpose=payment_id,
        amount_kopecks=amount,
        status=status,
        created_at=created_at,
        paid_at=paid_at,
        refunded_at=refunded_at,
    )


def _assert_invariants(test: unittest.TestCase, row) -> None:
    test.assertEqual(
        row.allocated_to_works_kopecks + row.overpayment_kopecks,
        row.paid_kopecks,
    )
    test.assertEqual(
        row.payable_kopecks - row.allocated_to_works_kopecks,
        row.remaining_kopecks,
    )
    if row.remaining_kopecks > 0:
        test.assertEqual(row.overpayment_kopecks, 0)


class TestRealDataAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = load_data(DATA_DIR)

    def _rows(self, as_of: date):
        report = allocate(self.dataset, as_of)
        works = {r.work_id: r for r in report.work_rows}
        contracts = {r.contract_id: r for r in report.contract_rows}
        return works, contracts

    def test_d1_on_2026_11_10(self) -> None:
        works, contracts = self._rows(date(2026, 11, 10))
        d1 = contracts["D-1"]
        self.assertEqual(d1.paid_kopecks, 315_000 * RUB)
        self.assertEqual(d1.payable_kopecks, 500_000 * RUB)
        self.assertEqual(d1.remaining_kopecks, 185_000 * RUB)
        self.assertEqual(d1.overpayment_kopecks, 0)

        self.assertEqual(works["W-11"].paid_total_kopecks, 100_000 * RUB)
        self.assertEqual(works["W-11"].remaining_kopecks, 0)
        self.assertEqual(works["W-12"].paid_total_kopecks, 100_000 * RUB)
        self.assertEqual(works["W-12"].remaining_kopecks, 0)

        self.assertEqual(works["W-13"].status_on_d, "cancelled")
        self.assertEqual(works["W-13"].remaining_kopecks, 0)

        self.assertEqual(works["W-14"].paid_bound_kopecks, 15_000 * RUB)
        self.assertEqual(works["W-14"].paid_from_pool_kopecks, 85_000 * RUB)
        self.assertEqual(works["W-14"].remaining_kopecks, 0)

        self.assertEqual(works["W-15"].paid_from_pool_kopecks, 15_000 * RUB)
        self.assertEqual(works["W-15"].paid_total_kopecks, 15_000 * RUB)
        self.assertEqual(works["W-15"].remaining_kopecks, 85_000 * RUB)

        self.assertEqual(works["W-16"].paid_total_kopecks, 0)
        self.assertEqual(works["W-16"].remaining_kopecks, 100_000 * RUB)

        self.assertEqual(d1.advance_for_planned_kopecks, 15_000 * RUB)
        _assert_invariants(self, d1)

    def test_d2_on_2026_11_10(self) -> None:
        works, contracts = self._rows(date(2026, 11, 10))
        d2 = contracts["D-2"]
        self.assertEqual(d2.paid_kopecks, 75_000 * RUB)
        self.assertEqual(d2.payable_kopecks, 90_000 * RUB)
        self.assertEqual(d2.remaining_kopecks, 15_000 * RUB)
        self.assertEqual(d2.overpayment_kopecks, 0)

        self.assertEqual(works["W-21"].paid_total_kopecks, 20_000 * RUB)
        self.assertEqual(works["W-21"].remaining_kopecks, 0)
        self.assertEqual(works["W-22"].paid_total_kopecks, 30_000 * RUB)
        self.assertEqual(works["W-22"].remaining_kopecks, 0)

        self.assertEqual(works["W-23"].status_on_d, "planned")
        self.assertEqual(works["W-23"].paid_total_kopecks, 25_000 * RUB)
        self.assertEqual(works["W-23"].remaining_kopecks, 15_000 * RUB)
        _assert_invariants(self, d2)

    def test_d2_on_2026_11_12(self) -> None:
        works, contracts = self._rows(date(2026, 11, 12))
        d2 = contracts["D-2"]
        self.assertEqual(d2.paid_kopecks, 95_000 * RUB)
        self.assertEqual(d2.overpayment_kopecks, 5_000 * RUB)
        self.assertEqual(works["W-23"].status_on_d, "done")
        self.assertEqual(works["W-23"].paid_total_kopecks, 40_000 * RUB)
        self.assertEqual(works["W-23"].remaining_kopecks, 0)
        _assert_invariants(self, d2)

    def test_invariants_on_real_data(self) -> None:
        for as_of in (date(2026, 11, 10), date(2026, 11, 12)):
            _, contracts = self._rows(as_of)
            for row in contracts.values():
                with self.subTest(as_of=as_of, contract=row.contract_id):
                    _assert_invariants(self, row)


class TestSynthetic(unittest.TestCase):
    def test_order_works_same_completed_at_by_work_id(self) -> None:
        day = date(2026, 10, 1)
        views = [
            WorkView(_work("W-B", completed_at=day), "done"),
            WorkView(_work("W-A", completed_at=day), "done"),
            WorkView(_work("W-C"), "planned"),
        ]
        ordered = order_works_for_pool(views)
        self.assertEqual([v.work.work_id for v in ordered], ["W-A", "W-B", "W-C"])

    def test_distribute_pool_fifo(self) -> None:
        day = date(2026, 10, 1)
        views = [
            WorkView(_work("W-A", price=50 * RUB, completed_at=day), "done"),
            WorkView(_work("W-B", price=50 * RUB, completed_at=day), "done"),
        ]
        ordered = order_works_for_pool(views)
        from_pool = distribute_pool(70 * RUB, ordered, {})
        self.assertEqual(from_pool["W-A"], 50 * RUB)
        self.assertEqual(from_pool["W-B"], 20 * RUB)

    def test_paid_at_equals_d_counts(self) -> None:
        payment = _payment("P-1", 10 * RUB, paid_at=date(2026, 11, 10))
        self.assertTrue(payment_counts(payment, date(2026, 11, 10)))

    def test_refunded_at_equals_d_excluded(self) -> None:
        payment = _payment(
            "P-r",
            10 * RUB,
            status="refunded",
            paid_at=date(2026, 9, 1),
            refunded_at=date(2026, 11, 10),
        )
        self.assertFalse(payment_counts(payment, date(2026, 11, 10)))

    def test_paid_before_d_refunded_after_counts(self) -> None:
        payment = _payment(
            "P-r",
            10 * RUB,
            status="refunded",
            paid_at=date(2026, 9, 1),
            refunded_at=date(2026, 11, 20),
        )
        self.assertTrue(payment_counts(payment, date(2026, 11, 10)))

    def test_queued_not_counted(self) -> None:
        payment = _payment("P-q", 10 * RUB, status="queued", paid_at=None)
        self.assertFalse(payment_counts(payment, date(2026, 11, 10)))

    def test_completed_at_equals_d_is_done(self) -> None:
        work = _work("W-1", completed_at=date(2026, 11, 10))
        self.assertEqual(work_status_on(work, date(2026, 11, 10)), "done")

    def test_cancelled_at_equals_d_is_cancelled(self) -> None:
        work = _work("W-1", cancelled_at=date(2026, 11, 10))
        self.assertEqual(work_status_on(work, date(2026, 11, 10)), "cancelled")

    def test_partial_pool_then_cancel_moves_to_next(self) -> None:
        contract = Contract("C-1", "X", 200 * RUB, date(2026, 1, 1))
        works = [
            Work(
                work_id="W-A",
                contract_id="C-1",
                title="W-A",
                price_kopecks=100 * RUB,
                status="cancelled",
                completed_at=date(2026, 2, 1),
                cancelled_at=date(2026, 3, 1),
            ),
            _work("W-B", price=100 * RUB, completed_at=date(2026, 2, 2)),
        ]
        payments = [_payment("P-1", 40 * RUB, paid_at=date(2026, 2, 10))]
        dataset = Dataset((contract,), tuple(works), tuple(payments))

        before = allocate(dataset, date(2026, 2, 15))
        works_before = {r.work_id: r for r in before.work_rows}
        self.assertEqual(works_before["W-A"].status_on_d, "done")
        self.assertEqual(works_before["W-A"].paid_from_pool_kopecks, 40 * RUB)
        self.assertEqual(works_before["W-B"].paid_total_kopecks, 0)

        after = allocate(dataset, date(2026, 3, 1))
        works_after = {r.work_id: r for r in after.work_rows}
        self.assertEqual(works_after["W-A"].status_on_d, "cancelled")
        self.assertEqual(works_after["W-A"].paid_total_kopecks, 0)
        self.assertEqual(works_after["W-B"].paid_from_pool_kopecks, 40 * RUB)
        _assert_invariants(self, after.contract_rows[0])

    def test_bound_on_cancelled_goes_to_pool_closes_other(self) -> None:
        contract = Contract("C-1", "X", 200 * RUB, date(2026, 1, 1))
        works = [
            _work("W-A", price=100 * RUB, cancelled_at=date(2026, 2, 1)),
            _work("W-B", price=100 * RUB, completed_at=date(2026, 2, 2)),
        ]
        payments = [
            _payment("P-1", 100 * RUB, work_id="W-A", paid_at=date(2026, 1, 15)),
        ]
        dataset = Dataset((contract,), tuple(works), tuple(payments))
        report = allocate(dataset, date(2026, 3, 1))
        works_map = {r.work_id: r for r in report.work_rows}
        row = report.contract_rows[0]
        self.assertEqual(works_map["W-A"].redirected_to_pool_kopecks, 100 * RUB)
        self.assertEqual(works_map["W-B"].paid_from_pool_kopecks, 100 * RUB)
        self.assertEqual(row.overpayment_kopecks, 0)
        self.assertEqual(row.remaining_kopecks, 0)
        _assert_invariants(self, row)

    def test_bound_over_price_excess_to_pool(self) -> None:
        contract = Contract("C-1", "X", 150 * RUB, date(2026, 1, 1))
        works = [
            _work("W-1", price=50 * RUB, completed_at=date(2026, 2, 1)),
            _work("W-2", price=100 * RUB, completed_at=date(2026, 2, 2)),
        ]
        payments = [
            _payment("P-1", 80 * RUB, work_id="W-1", paid_at=date(2026, 2, 15)),
        ]
        dataset = Dataset((contract,), tuple(works), tuple(payments))
        report = allocate(dataset, date(2026, 3, 1))
        works_map = {r.work_id: r for r in report.work_rows}
        row = report.contract_rows[0]
        self.assertEqual(works_map["W-1"].paid_bound_kopecks, 50 * RUB)
        self.assertEqual(works_map["W-1"].redirected_to_pool_kopecks, 30 * RUB)
        self.assertEqual(works_map["W-2"].paid_from_pool_kopecks, 30 * RUB)
        self.assertEqual(row.overpayment_kopecks, 0)
        self.assertEqual(row.remaining_kopecks, 70 * RUB)
        _assert_invariants(self, row)

    def test_bound_over_price_alone_is_overpayment(self) -> None:
        contract = Contract("C-1", "X", 50 * RUB, date(2026, 1, 1))
        works = [_work("W-1", price=50 * RUB, completed_at=date(2026, 2, 1))]
        payments = [_payment("P-1", 80 * RUB, work_id="W-1", paid_at=date(2026, 2, 15))]
        dataset = Dataset((contract,), tuple(works), tuple(payments))
        report = allocate(dataset, date(2026, 3, 1))
        row = report.contract_rows[0]
        work = report.work_rows[0]
        self.assertEqual(work.paid_total_kopecks, 50 * RUB)
        self.assertEqual(work.redirected_to_pool_kopecks, 30 * RUB)
        self.assertEqual(row.overpayment_kopecks, 30 * RUB)
        _assert_invariants(self, row)

    def test_two_contracts_pools_isolated(self) -> None:
        contracts = (
            Contract("C-1", "A", 100 * RUB, date(2026, 1, 1)),
            Contract("C-2", "B", 100 * RUB, date(2026, 1, 1)),
        )
        works = (
            _work("W-1", "C-1", 100 * RUB, completed_at=date(2026, 2, 1)),
            _work("W-2", "C-2", 100 * RUB, completed_at=date(2026, 2, 1)),
        )
        payments = (_payment("P-1", 100 * RUB, contract_id="C-1", paid_at=date(2026, 2, 10)),)
        dataset = Dataset(contracts, works, payments)
        report = allocate(dataset, date(2026, 3, 1))
        by_c = {r.contract_id: r for r in report.contract_rows}
        works_map = {r.work_id: r for r in report.work_rows}
        self.assertEqual(works_map["W-1"].paid_total_kopecks, 100 * RUB)
        self.assertEqual(works_map["W-2"].paid_total_kopecks, 0)
        self.assertEqual(by_c["C-2"].paid_kopecks, 0)
        _assert_invariants(self, by_c["C-1"])
        _assert_invariants(self, by_c["C-2"])


if __name__ == "__main__":
    unittest.main()
