import os
try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    print("Warning: faiss not found. Using simple fallback memory.")

import numpy as np
import json
import time
from datetime import datetime
try:
    from sentence_transformers import SentenceTransformer
    ST_AVAILABLE = True
except ImportError:
    ST_AVAILABLE = False
    print("Warning: sentence_transformers not found. Semantic memory will be disabled.")

# Path to save/load index and metadata
INDEX_FILE = "memory_index.faiss"
METADATA_FILE = "memory_metadata.json"
MODEL_NAME = "all-MiniLM-L6-v2"

class MemoryEngine:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MemoryEngine, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        if ST_AVAILABLE:
            print("Loading Embedding Model...")
            self.model = SentenceTransformer(MODEL_NAME)
            self.dimension = 384  # Dimension for all-MiniLM-L6-v2
        else:
            self.model = None
            self.dimension = 0
        
        # Load or Create Index
        if FAISS_AVAILABLE:
            if os.path.exists(INDEX_FILE) and os.path.exists(METADATA_FILE):
                print("Loading existing FAISS index...")
                self.index = faiss.read_index(INDEX_FILE)
                with open(METADATA_FILE, 'r') as f:
                    self.metadata = json.load(f)
            else:
                print("Creating new FAISS index...")
                self.index = faiss.IndexFlatL2(self.dimension)
                self.metadata = [] 
        else:
            # Fallback to simple list-based storage
            self.index = None # Will use metadata for similarity
            if os.path.exists(METADATA_FILE):
                with open(METADATA_FILE, 'r') as f:
                    self.metadata = json.load(f)
            else:
                self.metadata = []

    def store_memory(self, text: str, meta: dict = None):
        """
        Stores a memory with associated metadata.
        meta should include 'timestamp', 'type' (e.g., 'task_completion', 'event'), 'uid'.
        """
        from ai.classifier import classify_text  # Import here to avoid circular dependency if any
        
        if not text:
            return

        if ST_AVAILABLE and self.model is not None:
             vector = self.model.encode([text])[0]
             if FAISS_AVAILABLE and self.index is not None:
                  self.index.add(np.array([vector], dtype=np.float32))
        else:
             print("MemoryEngine: Skipping vectorization (Model unavailable)")
        
        # We always store in metadata for fallback/info
        if meta is None:
            meta = {}
            
        # Ensure timestamp exists
        if 'timestamp' not in meta:
            meta['timestamp'] = datetime.now().isoformat()
            
        # Auto-classify
        if 'category' not in meta:
             meta['category'] = classify_text(text)

        entry_id = len(self.metadata)
        meta['text'] = text
        meta['id'] = entry_id
        
        self.metadata.append(meta)
        self._save()
        print(f"Stored memory: {text} | Cat: {meta['category']}")

    def recall(self, query: str, uid: str = None, top_k: int = 3, 
               time_range: tuple = None, distance_threshold: float = 1.2,
               category_filter: str = None, sort_by_time: bool = False):
        """
        Recalls memories based on semantic similarity with advanced filtering/scoring.
        start_dt, end_dt: Strict time window.
        category_filter: If provided, boosts score of matching memories.
        sort_by_time: If True, ignores semantic distance for ranking (returns most recent logic).
        """
        # candidates list
        candidates = []
        now = datetime.now()

        if ST_AVAILABLE and self.model is not None:
            query_vector = self.model.encode([query])[0]
            if FAISS_AVAILABLE and self.index is not None:
                # Fetch many candidates to apply filters/decay
                D, I = self.index.search(np.array([query_vector], dtype=np.float32), top_k * 10)
                indices = I[0]
                distances = D[0]
            else:
                # Simple linear scan fallback with embeddings if ST is available
                print("MemoryEngine: Using linear scan with embeddings...")
                indices = range(len(self.metadata))
                distances = []
                for item in self.metadata:
                    item_text = item.get('text', '')
                    item_vector = self.model.encode([item_text])[0]
                    dist = np.linalg.norm(query_vector - item_vector)
                    distances.append(dist)
        else:
            # Full fallback: just keyword matching or recent items
            print("MemoryEngine: Full fallback to recent items (No AI)...")
            indices = list(range(len(self.metadata)))[::-1] # Newest first
            distances = [0.0] * len(indices)
        
        for i, idx in enumerate(indices):
            if idx == -1: continue 
            
            raw_dist = float(distances[i]) if distances else 0.0
            item = self.metadata[idx]
            
            # --- 1. Hard Filters ---
            if uid and item.get('uid') != uid:
                continue
                
            mem_time = None
            try:
                mem_time = datetime.fromisoformat(item['timestamp'])
            except:
                continue # Skip invalid dates
                
            if time_range:
                start_dt, end_dt = time_range
                if not (start_dt <= mem_time <= end_dt):
                    continue

            # --- 2. Scoring Logic (Decay + Boost) ---
            final_score = raw_dist
            
            # Decay: Penalty for age. 
            # E.g., +0.01 per day. 30 days = +0.3 dist.
            days_old = (now - mem_time).days
            if days_old > 0:
                decay_penalty = days_old * 0.005 # Mild decay
                # Cap decay to avoid overpowering semantics completely?
                final_score += min(decay_penalty, 0.5) 

            # Boost: Bonus for Category Match
            # E.g., -0.2 dist.
            if category_filter and item.get('category') == category_filter:
                final_score -= 0.3
            
            # Threshold Check (skip if *really* bad match, unless sorting by time?)
            # If sorting by time, we might accept looser matches because intent is "When did I LAST..."
            # But we still want "When did I last take MEDS" to not return "I walked dog".
            # So apply a loose Semantic Threshold even for time-sort.
            loose_threshold = distance_threshold + 0.5 # Allow slightly more flexible matching
            if not sort_by_time and final_score > distance_threshold:
                 continue
            if sort_by_time and raw_dist > loose_threshold: # Check RAW distance for semantic relevance
                 continue

            candidates.append({
                "text": item['text'],
                "metadata": item,
                "score": final_score,
                "raw_dist": raw_dist,
                "timestamp": mem_time,
                "cat_match": category_filter and item.get('category') == category_filter
            })

        # --- 3. Sorting ---
        if sort_by_time:
            # Sort by Category Match (True first), then Timestamp (Newest first)
            candidates.sort(key=lambda x: (x['cat_match'], x['timestamp']), reverse=True)
        else:
            # Best score (lowest) first
            candidates.sort(key=lambda x: x['score'])
            
        return candidates[:top_k]

    def _save(self):
        if FAISS_AVAILABLE and self.index is not None:
            faiss.write_index(self.index, INDEX_FILE)
        with open(METADATA_FILE, 'w') as f:
            json.dump(self.metadata, f)

# Global Accessor
memory_engine = MemoryEngine()
