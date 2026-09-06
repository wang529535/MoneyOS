from decimal import Decimal
import unittest

from moneyos.errors import ValidationError
from moneyos.money import format_minor_units, normalize_currency, parse_minor_units


class MoneyTests(unittest.TestCase):
    def test_exact_minor_units(self):
        self.assertEqual(parse_minor_units("0.01"), 1)
        self.assertEqual(parse_minor_units("238"), 23800)
        self.assertEqual(parse_minor_units(Decimal("12.30")), 1230)
        self.assertEqual(format_minor_units(1230, "CNY"), "CNY 12.30")
        self.assertEqual(format_minor_units(-1), "-0.01")

    def test_rejects_float_and_excess_precision(self):
        with self.assertRaises(ValidationError):
            parse_minor_units(0.1)
        with self.assertRaises(ValidationError):
            parse_minor_units("0.001")
        with self.assertRaises(ValidationError):
            parse_minor_units("NaN")
        with self.assertRaises(ValidationError):
            parse_minor_units("not money")

    def test_zero_policy(self):
        with self.assertRaises(ValidationError):
            parse_minor_units("0")
        self.assertEqual(parse_minor_units("0", allow_zero=True), 0)
        with self.assertRaises(ValidationError):
            parse_minor_units("-1", allow_zero=True)

    def test_currency_normalization(self):
        self.assertEqual(normalize_currency(" cny "), "CNY")
        for invalid in ("CN", "USDT", "12A", "人民币"):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                normalize_currency(invalid)


if __name__ == "__main__":
    unittest.main()
