import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.extractor import extract_patterns, hybrid_enrich_medication

def test_high_quality_enrichment():
    print("Running High-Quality Extraction Tests...")
    
    # 1. Shorthand to Pattern mapping
    print("\nTesting Shorthand to Pattern:")
    patterns = extract_patterns("Allegra 120mg OD pc")
    print(f"  'OD pc' -> dose_pattern: {patterns['dose_pattern']} (Expected: 1-0-0)")
    assert patterns['dose_pattern'] == "1-0-0"
    
    # 2. Drug Name Cleaning (Brand Noise)
    print("\nTesting Drug Name Cleaning (ventek):")
    med = {"drug_name": "Motelukast ventek", "raw_text": "Motelukast ventek 10mg OD"}
    enriched = hybrid_enrich_medication(med)
    print(f"  'Motelukast ventek' -> drug_name: {enriched['drug_name']} (Expected: Montelukast)")
    assert enriched['drug_name'] == "Montelukast"
    
    # 3. Pattern Detection (1-0-1)
    print("\nTesting Explicit Dose Pattern:")
    patterns = extract_patterns("Losartan 50mg 1-0-1")
    print(f"  '1-0-1' -> dose_pattern: {patterns['dose_pattern']} (Expected: 1-0-1)")
    assert patterns['dose_pattern'] == "1-0-1"
    
    # 4. Duration Parsing
    print("\nTesting Duration Parsing:")
    patterns = extract_patterns("Allegra for 14 days")
    print(f"  'for 14 days' -> duration_days: {patterns['duration_days']} (Expected: 14)")
    assert patterns['duration_days'] == 14

    print("\n✅ ALL HIGH-QUALITY EXTRACTION TESTS PASSED!")

if __name__ == "__main__":
    test_high_quality_enrichment()
