from ai.memory_engine import memory_engine
from ai.time_utils import extract_time_range
import time
from datetime import datetime

def test_full_pipeline():
    print("--- 1. Resetting/Initializing Engine ---")
    engine = memory_engine
    # Clear metadata for clean test if desired, or just use unique UID
    test_uid = f"time_test_{int(time.time())}"
    
    # Store memories with different "imagined" timestamps? 
    # Our simple MemoryEngine defaults to NOW() for timestamp.
    # To test time filtering properly without waiting days, we must hack the metadata 
    # OR forcefully insert tasks with old timestamps.
    
    # Let's manually inject memories with specific timestamps into the engine's list
    # (Since store_memory defaults to NOW, we will manually append to metadata/index)
    
    print(f"Test UID: {test_uid}")
    
    # 1. Store "Old" Memory (Last week)
    print("Injecting old memory...")
    engine.store_memory("I went to the dentist.", {"uid": test_uid})
    # Hack: modify the last entry's timestamp to be 7 days ago
    engine.metadata[-1]['timestamp'] = "2023-01-01T12:00:00.000000" # Very old
    
    # 2. Store "New" Memory (Today)
    print("Injecting new memory...")
    engine.store_memory("I ate an apple.", {"uid": test_uid})
    # Keep timestamp as NOW (default)
    
    print("\n--- 2. Testing Queries ---")
    
    # Case A: "Did I go to the dentist today?" -> Should fail (timestamp mismatch)
    query = "Did I go to the dentist today?"
    print(f"\nQuery: {query}")
    t_range = extract_time_range(query)
    print(f"  -> Extracted Range: {t_range}")
    res = engine.recall("go to dentist", uid=test_uid, time_range=t_range)
    print(f"  -> Result count: {len(res)}")
    if len(res) == 0:
        print("  -> SUCCESS: Correctly filtered out old memory.")
    else:
        top = res[0]
        print(f"  -> FAILURE: Found unexpected memory: {top['text']} (Score: {top['score']:.4f})")

    # Case B: "Did I eat an apple today?" -> Should succeed
    query = "Did I eat an apple today?"
    print(f"\nQuery: {query}")
    t_range = extract_time_range(query)
    res = engine.recall("eat apple", uid=test_uid, time_range=t_range)
    if len(res) > 0:
        print(f"  -> SUCCESS: Found memory: {res[0]['text']}")
    else:
        print("  -> FAILURE: Could not find recent memory.")

if __name__ == "__main__":
    test_full_pipeline()
