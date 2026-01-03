from ai.memory_engine import memory_engine
import time

def test_engine():
    print("--- 1. Initializing Engine ---")
    # This might take a moment to load the model
    engine = memory_engine
    print("Engine loaded.")

    print("\n--- 2. Storing Memories ---")
    memories = [
        "I took my blood pressure medication at 9 AM.",
        "I went for a walk in the park yesterday.",
        "My daughter promised to visit me this weekend.",
        "I finished lunch at 1 PM."
    ]
    
    for m in memories:
        engine.store_memory(m, {"uid": "test_user_1"})
        
    print(f"Stored {len(memories)} memories.")

    print("\n--- 3. Testing Recall (Similarity) ---")
    queries = [
        "Did I take my meds?",
        "What did I do yesterday?",
        "Who is visiting me?",
        "Did I eat lunch?"
    ]
    
    for q in queries:
        print(f"\nQuery: '{q}'")
        results = engine.recall(q, uid="test_user_1", top_k=1)
        if results:
            top = results[0]
            print(f"  -> Best Match: {top['text']} (Score: {top['score']:.4f})")
        else:
            print("  -> No match found.")

    print("\n--- 4. Testing Time Filter ---")
    # This relies on the timestamp we just added being 'fresh'
    print("Query: 'What did I do today?' (Day filter=1)")
    results = engine.recall("What did I do?", uid="test_user_1", time_filter_days=1)
    print(f"  -> Found {len(results)} results from today.")

if __name__ == "__main__":
    test_engine()
