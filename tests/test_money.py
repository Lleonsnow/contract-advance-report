import unittest

from advance.money import format_rub, format_rub_csv, parse_kopecks


class TestParseKopecks(unittest.TestCase):
    def test_valid(self) -> None:
        self.assertEqual(parse_kopecks("0.00", source="t.csv", line_no=1), 0)
        self.assertEqual(parse_kopecks("123.45", source="t.csv", line_no=2), 12345)
        self.assertEqual(parse_kopecks("100000.00", source="t.csv", line_no=3), 10000000)

    def test_invalid(self) -> None:
        for raw in ("100", "100.0", "100.000", "1,00"):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError) as ctx:
                    parse_kopecks(raw, source="payments.csv", line_no=7)
                message = str(ctx.exception)
                self.assertIn("payments.csv", message)
                self.assertIn("7", message)


class TestFormatRub(unittest.TestCase):
    def test_format_rub(self) -> None:
        self.assertEqual(format_rub(0), "0,00")
        self.assertEqual(format_rub(12345), "123,45")
        self.assertEqual(format_rub(123456), "1 234,56")
        self.assertEqual(format_rub(31500000), "315 000,00")

    def test_format_rub_csv(self) -> None:
        self.assertEqual(format_rub_csv(123456), "1234,56")
        self.assertEqual(format_rub_csv(31500000), "315000,00")


if __name__ == "__main__":
    unittest.main()
