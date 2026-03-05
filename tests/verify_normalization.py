import sys
import os

# Add parent directory to path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api.routes.ai_routes import normalize_timing
from app.services.ocr_fallback import guess_timing, guess_freq

def test_normalization():
    print("Running Normalization Tests...")
    
    # Timing Tests
    t1 = normalize_timing("ac")
    print(f"normalize_timing('ac') -> {t1}")
    assert t1 == "before_meal"
    
    t2 = normalize_timing("HS")
    print(f"normalize_timing('HS') -> {t2}")
    assert t2 == "bedtime"
    
    print("âœ… timing normalization passed")

    # OCR Fallback Timing Tests
    g1 = guess_timing("Take at bedtime")
    print(f"guess_timing('Take at bedtime') -> {g1}")
    assert g1 == "bedtime"
    
    g2 = guess_timing("1 tab pc")
    print(f"guess_timing('1 tab pc') -> {g2}")
    assert g2 == "after_meal"
    
    print("âœ… guess_timing passed")

    # Frequency Tests
    f_val, f_token = guess_freq("Allegra 120mg BD")
    print(f"guess_freq('Allegra 120mg BD') -> {f_val}, {f_token}")
    assert f_val == 2
    assert f_token == "BD"
    
    print("âœ… frequency guessing passed")

if __name__ == "__main__":
    try:
        test_normalization()
        print("\nALL NORMALIZATION TESTS PASSED!")
    except AssertionError as e:
        print(f"\nTEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        sys.exit(1)
