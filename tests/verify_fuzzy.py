import sys
import os

# Add parent directory to path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.extractor import normalize_drug_name

def test_fuzzy_matching():
    print("Running Fuzzy Matching Tests...")
    
    test_cases = [
        ("Paracetmol", "Paracetamol"),
        ("Alegra", "Allegra"),
        ("Losrtan", "Losartan"),
        ("Metformin 500", "Metformin"), # Should still match if score is high
        ("UnknownDrugXYZ", "UnknownDrugXYZ"), # Should stay same if no match found with high enough score
    ]
    
    passed = 0
    for input_name, expected in test_cases:
        result = normalize_drug_name(input_name)
        print(f"normalize_drug_name('{input_name}') -> '{result}' (Expected: '{expected}')")
        if result == expected:
            passed += 1
        else:
            print(f"  FAILED: '{result}' != '{expected}'")
            
    if passed == len(test_cases):
        print("\n✅ ALL FUZZY MATCHING TESTS PASSED!")
    else:
        print(f"\n❌ {len(test_cases) - passed} TESTS FAILED.")
        sys.exit(1)

if __name__ == "__main__":
    test_fuzzy_matching()
