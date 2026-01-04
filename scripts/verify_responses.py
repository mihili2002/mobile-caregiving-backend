from ai.response_builder import build_recall_response
from datetime import datetime
import json

def test_full_response_flow():
    print("--- Testing Response Logic ---")
    
    # 1. High Confidence
    memories = [
        {"text": "I watered the plants.", "score": 0.5, "metadata": {"timestamp": datetime.now().isoformat()}}
    ]
    # Simulate Logic in Route
    uncertainty = "high" # score < 0.9
    resp = build_recall_response(memories, None, uncertainty)
    print(f"\n[High Conf] Input: {memories[0]['text']}")
    print(f"Output: {resp}")
    
    # 2. Ambiguity
    memories = [
        {"text": "Took blue pill", "score": 1.0, "metadata": {"timestamp": datetime.now().isoformat()}},
        {"text": "Took red pill", "score": 1.05, "metadata": {"timestamp": datetime.now().isoformat()}}
    ]
    # Simulate Logic
    # diff = 0.05 < 0.1 -> Ambiguous
    uncertainty = "ambiguous"
    resp = build_recall_response(memories, None, uncertainty)
    print(f"\n[Ambiguous] Input: Blue Pill (1.0) vs Red Pill (1.05)")
    print(f"Output: {resp}")

    # 3. Not Found (Low Confidence)
    # Score > 1.2
    memories = [] # Logic filters this out
    resp = build_recall_response([], None, "low")
    print(f"\n[Not Found] Input: Empty/Filtered")
    print(f"Output: {resp}")

if __name__ == "__main__":
    test_full_response_flow()
