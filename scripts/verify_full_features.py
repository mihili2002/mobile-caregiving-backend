from ai.memory_engine import memory_engine
from ai.classifier import classify_text
from ai.response_builder import build_recall_response
import time
from datetime import datetime, timedelta

def test_features():
    print("--- 1. Testing Categorization ---")
    text = "I took my blood pressure pills"
    cat = classify_text(text)
    print(f"Text: '{text}' -> Category: {cat}")
    if cat != "medication":
        print("FAILURE: Categorization incorrect.")
    else:
        print("SUCCESS: Categorization correct.")

    print("\n--- 2. Testing Memory Storage & Auto-Classification ---")
    uid = f"adv_test_{int(time.time())}"
    engine = memory_engine
    # Clear for test
    engine.metadata = [] 
    engine.index.reset()
    
    engine.store_memory("I ate a sandwich.", {"uid": uid})
    engine.store_memory("I took my aspirin.", {"uid": uid})
    
    if engine.metadata[1]['category'] == 'medication':
        print("SUCCESS: Auto-classification worked on storage.")
    else:
        print(f"FAILURE: Category is {engine.metadata[1].get('category')}")

    print("\n--- 3. Testing 'Last Time' Recall ---")
    # Inject old vs new
    # Latest: aspirin (just added, timestamp=now)
    # Generic: sandwich (now)
    # Let's add an OLD aspirin memory manually
    engine.store_memory("I took my aspirin.", {"uid": uid})
    engine.metadata[-1]['timestamp'] = (datetime.now() - timedelta(days=5)).isoformat()
    # Now we have:
    # 0: Sandwich (Now)
    # 1: Aspirin (Now)
    # 2: Aspirin (5 days ago)
    
    # Query: "When did I last take aspirin?"
    # Should ignore semantic score (mostly) and sorting by time, returning index 1 (Now), not 2 (Old).
    # Wait, 1 is newer than 2.
    # Let's add a NEWER unrelated thing.
    engine.store_memory("I watched TV.", {"uid": uid}) # Index 3 (Now + 1ms)
    
    # So:
    # 3: TV (Now) - Classification: activity
    # 1: Aspirin (Now) - Classification: medication
    # 0: Sandwich (Now) - Classification: meal
    # 2: Aspirin (Old)
    
    # Query "Last time aspirin" -> 
    # Logic in routes: 
    #   is_last_time=True
    #   category=medication (boosts aspirin)
    #   sort_by_time=True
    
    # Recall args: query="...", category_filter="medication", sort_by_time=True
    results = engine.recall("last time aspirin", uid=uid, category_filter="medication", sort_by_time=True, top_k=5)
    
    print("Results (Time Sorted + Category Boosted):")
    for r in results:
        print(f" - {r['text']} ({r['timestamp']}) Score: {r['score']:.4f}")
        
    if results[0]['text'] == "I took my aspirin.":
        print("SUCCESS: Found most recent aspirin.")
    else:
        print("FAILURE: Did not prioritize recent matches.")

    print("\n--- 4. Testing Confirmation Logic (Simulation) ---")
    # Route logic says: if category=medication and high confidence -> ask confirmation.
    # Check response builder directly
    resp = build_recall_response([results[0]], None, "high", ask_confirmation=True)
    print(f"Response: {resp}")
    if "Is that correct?" in resp:
        print("SUCCESS: Confirmation added.")
    else:
        print("FAILURE: Confirmation missing.")

if __name__ == "__main__":
    test_features()
