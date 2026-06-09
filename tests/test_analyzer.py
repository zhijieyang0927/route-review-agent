import unittest

from route_review_agent.analyzer import analyze_round
from route_review_agent.guided import _extract_api_key
from route_review_agent.io import load_orders
from route_review_agent.models import normalize_vehicle_type


class AnalyzerTest(unittest.TestCase):
    def test_flags_controlled_delay_with_input_expected_baseline(self):
        orders = load_orders("examples/sample_orders.csv")
        result = analyze_round(orders, screenshots=[])
        self.assertEqual(result.conclusion_level, "明显异常")
        abnormal = [s for s in result.segments if s.level == "明显异常"]
        self.assertTrue(abnormal)
        self.assertTrue(all(s.rider_controlled for s in abnormal))

    def test_restaurant_wait_not_directly_attributed(self):
        orders = load_orders("examples/sample_orders.csv")
        result = analyze_round(orders, screenshots=[])
        waits = [s for s in result.segments if s.segment_type == "到店等餐"]
        self.assertTrue(waits)
        self.assertTrue(all(not s.rider_controlled for s in waits))

    def test_chinese_vehicle_aliases(self):
        self.assertEqual(normalize_vehicle_type("电动车"), "ebike")
        self.assertEqual(normalize_vehicle_type("摩托车"), "moped")
        self.assertEqual(normalize_vehicle_type("汽车"), "car")

    def test_extracts_api_key_from_opening_phrase(self):
        self.assertEqual(_extract_api_key("订单复盘，Google map API是ABC_123-test"), "ABC_123-test")


if __name__ == "__main__":
    unittest.main()
