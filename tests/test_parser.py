from __future__ import annotations

import unittest

from moneyos.parser import DeterministicParser, ParseError


class DeterministicParserTests(unittest.TestCase):
    def setUp(self):
        self.parser = DeterministicParser()

    def test_simple_expense(self):
        result = self.parser.parse("麦当劳26")
        self.assertEqual(result.kind, "expense")
        self.assertEqual(result.payload["amount_minor"], 2600)
        self.assertEqual(result.payload["payee"], "麦当劳")
        self.assertEqual(result.missing_fields, ("account", "category"))
        self.assertTrue(result.requires_confirmation)

    def test_full_width_input_is_normalized_for_parsing(self):
        result = self.parser.parse("地铁２．５０元")
        self.assertEqual(result.payload["amount_minor"], 250)
        self.assertEqual(result.payload["description"], "地铁")

    def test_income(self):
        result = self.parser.parse("妈妈给了500")
        self.assertEqual(result.kind, "income")
        self.assertEqual(result.payload["amount_minor"], 50_000)
        self.assertEqual(result.payload["payee"], "妈妈")

    def test_transfer(self):
        result = self.parser.parse("从银行卡转100到支付宝")
        self.assertEqual(result.kind, "transfer")
        self.assertEqual(result.payload["from_account"], "银行卡")
        self.assertEqual(result.payload["to_account"], "支付宝")
        self.assertEqual(result.payload["amount_minor"], 10_000)
        self.assertEqual(result.missing_fields, ())

    def test_shared_expense_with_settlement(self):
        result = self.parser.parse("和小李吃海底捞我先付238，他后来转我100")
        self.assertEqual(result.kind, "expense")
        self.assertEqual(result.payload["amount_minor"], 23_800)
        self.assertEqual(result.payload["personal_minor"], 13_800)
        self.assertEqual(result.payload["settled_minor"], 10_000)
        self.assertEqual(result.payload["owed_by"], "小李")
        self.assertGreater(result.confidence, 0.8)

    def test_ambiguous_or_invalid_input_fails_closed(self):
        for content in (
            "没有金额",
            "早餐10午餐20",
            "我先付10，他后来转我20",
            "退款26",
            "午饭-10",
            "   ",
        ):
            with self.subTest(content=content), self.assertRaises(ParseError):
                self.parser.parse(content)


if __name__ == "__main__":
    unittest.main()
