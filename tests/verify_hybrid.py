import sys
import os

# Add parent directory to path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.extractor import hybrid_enrich_medication

def test_hybrid_enrichment():
    print("Running Hybrid Enrichment Tests...")
    
    test_cases = [
        {
            "name": "Full Enrichment (Regex + Fuzzy)",
            "input": {
                "drug_name": "Paracetmol",
                "frequency_per_day": None,
                "timing": "unknown",
                "raw_text": "Paracetmol 500mg TDS pc x 10 days"
            },
            "expected": {
                "drug_name": "Paracetamol",
                "frequency_per_day": 3,
                "timing": "after_meal",
                "duration_days": 10
            }
        },
        {
            "name": "Dose Pattern (1-0-1)",
            "input": {
                "drug_name": "Losartan",
                "raw_text": "Tab. Losartan 50mg 1-0-1 for 30 days"
            },
            "expected": {
                "drug_name": "Losartan",
                "dose_pattern": "1-0-1",
                "frequency_per_day": 2
            }
        },
        {
            "name": "PRN Detection",
            "input": {
                "drug_name": "Ibuprofen",
                "is_prn": False,
                "raw_text": "Ibuprofen 400mg SOS"
            },
            "expected": {
                "drug_name": "Ibuprofen",
                "is_prn": True
            }
        }
    ]
    
    passed = 0
    for case in test_cases:
        print(f"\nTesting: {case['name']}")
        result = hybrid_enrich_medication(case['input'])
        
        case_passed = True
        for key, expected_val in case['expected'].items():
            actual_val = result.get(key)
            if actual_val == expected_val:
                print(f"  ✅ {key}: {actual_val}")
            else:
                print(f"  ❌ {key}: {actual_val} (Expected: {expected_val})")
                case_passed = False
        
        if case_passed:
            passed += 1
            
    if passed == len(test_cases):
        print("\n✅ ALL HYBRID ENRICHMENT TESTS PASSED!")
    else:
        print(f"\n❌ {len(test_cases) - passed} TESTS FAILED.")
        sys.exit(1)

if __name__ == "__main__":
    test_hybrid_enrichment()
