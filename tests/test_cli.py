import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from report import main

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _run(argv: list[str]) -> int:
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return main(argv)


class TestCli(unittest.TestCase):
    def test_success_writes_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_name:
            out = Path(tmp_name) / "out.csv"
            code = _run(
                [
                    "--data",
                    str(DATA_DIR),
                    "--date",
                    "2026-11-10",
                    "--csv",
                    str(out),
                ]
            )
            self.assertEqual(code, 0)
            raw = out.read_bytes()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
            text = raw.decode("utf-8-sig")
            self.assertIn(";", text.splitlines()[0])
            self.assertIn("Перенесено в пул", text.splitlines()[0])
            self.assertIn("выполнена", text)
            payments = out.with_name(f"{out.stem}_payments.csv")
            self.assertTrue(payments.exists())
            pay_raw = payments.read_bytes()
            self.assertTrue(pay_raw.startswith(b"\xef\xbb\xbf"))
            pay_text = pay_raw.decode("utf-8-sig")
            self.assertIn("Куда пошёл", pay_text.splitlines()[0])
            self.assertIn("P-1", pay_text)

    def test_bad_data_returns_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            (tmp / "contracts.csv").write_text(
                "contract_id,contractor,amount,signed_at\nC-1,X,bad,2026-01-01\n",
                encoding="utf-8",
            )
            (tmp / "works.csv").write_text(
                "work_id,contract_id,title,price,status,completed_at,cancelled_at\n",
                encoding="utf-8",
            )
            (tmp / "payments.csv").write_text(
                "payment_id,contract_id,work_id,purpose,amount,status,"
                "created_at,paid_at,refunded_at\n",
                encoding="utf-8",
            )
            code = _run(["--data", str(tmp), "--date", "2026-11-10"])
            self.assertEqual(code, 1)

    def test_csv_inside_data_returns_1(self) -> None:
        code = _run(
            [
                "--data",
                str(DATA_DIR),
                "--date",
                "2026-11-10",
                "--csv",
                str(DATA_DIR / "out.csv"),
            ]
        )
        self.assertEqual(code, 1)
        self.assertFalse((DATA_DIR / "out.csv").exists())


if __name__ == "__main__":
    unittest.main()
