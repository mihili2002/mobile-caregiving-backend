import unittest
from ai.response_builder import build_recall_response
from datetime import datetime

class TestResponseBuilder(unittest.TestCase):
    def test_low_uncertainty(self):
        resp = build_recall_response([], None, "low")
        self.assertIn("couldn't find", resp)
        
    def test_high_confidence(self):
        memories = [
            {"text": "Ate lunch", "metadata": {"timestamp": datetime.now().isoformat()}, "score": 0.5}
        ]
        resp = build_recall_response(memories, None, "high")
        self.assertTrue(resp.startswith("I remember: "))
        self.assertIn("Ate lunch", resp)
        self.assertIn("Today at", resp) # Check timestamp formatting

    def test_ambiguity(self):
        memories = [
            {"text": "Meds A", "metadata": {"timestamp": datetime.now().isoformat()}},
            {"text": "Meds B", "metadata": {"timestamp": datetime.now().isoformat()}}
        ]
        resp = build_recall_response(memories, None, "ambiguous")
        self.assertIn("I found two similar memories", resp)
        self.assertIn("Did you mean", resp)

if __name__ == '__main__':
    unittest.main()
