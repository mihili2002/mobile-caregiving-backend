import unittest
from datetime import datetime, time, timedelta
from ai.time_utils import extract_time_range

class TestTimeUtils(unittest.TestCase):
    def test_today(self):
        text = "What did I do today?"
        start, end = extract_time_range(text)
        now = datetime.now()
        self.assertEqual(start.date(), now.date())
        self.assertEqual(end.date(), now.date())
        self.assertEqual(start.time(), time.min)
        self.assertEqual(end.time(), time.max)

    def test_yesterday(self):
        text = "Did I take meds yesterday?"
        start, end = extract_time_range(text)
        now = datetime.now()
        expected_date = now.date() - timedelta(days=1)
        self.assertEqual(start.date(), expected_date)
        self.assertEqual(end.date(), expected_date)

    def test_this_morning(self):
        text = "I went for a walk this morning"
        start, end = extract_time_range(text)
        now = datetime.now()
        self.assertEqual(start, datetime.combine(now.date(), time(5, 0)))
        self.assertEqual(end, datetime.combine(now.date(), time(12, 0)))

    def test_last_week(self):
        text = "What happened last week?"
        start, end = extract_time_range(text)
        # Just check types and order, exact date logic is relative
        self.assertTrue(start < end)
        self.assertIsInstance(start, datetime)

    def test_no_time(self):
        text = "I like pizza"
        result = extract_time_range(text)
        self.assertIsNone(result)

if __name__ == '__main__':
    unittest.main()
