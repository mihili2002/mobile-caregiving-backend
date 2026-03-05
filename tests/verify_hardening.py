import sys
import os
import re
from typing import Optional

# Add parent directory to path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.api.routes.ai_routes import normalize_timing, parse_duration_days, clean_drug_prefix
from app.services.ocr_fallback import guess_timing, guess_freq, normalize_strength, guess_dose_form

def test_hardening():
    print("Running Hardening Tests...")
    
    # 1. Timing Enum (via normalize_timing)
    t1 = normalize_timing("ac")
    print(f"normalize_timing('ac') -> {t1}")
    assert t1 == "before_meal"
    
    # 2. Strength Normalization
    s1 = normalize_strength("500mg")
    print(f"normalize_strength('500mg') -> '{s1}'")
    assert s1 == "500 mg"
    
    s2 = normalize_strength("10ml")
    print(f"normalize_strength('10ml') -> '{s2}'")
    assert s2 == "10 ml"

    # 3. Duration Parsing
    d1 = parse_duration_days("2 weeks")
    print(f"parse_duration_days('2 weeks') -> {d1}")
    assert d1 == 14
    
    d2 = parse_duration_days("1 month")
    print(f"parse_duration_days('1 month') -> {d2}")
    assert d2 == 30
    
    d3 = parse_duration_days("10d")
    print(f"parse_duration_days('10d') -> {d3}")
    assert d3 == 10

    # 4. Drug Prefix Stripping
    n1 = clean_drug_prefix("Tab. Allegra")
    print(f"clean_drug_prefix('Tab. Allegra') -> '{n1}'")
    assert n1 == "Allegra"
    
    n2 = clean_drug_prefix("Cap Amoxicillin")
    print(f"clean_drug_prefix('Cap Amoxicillin') -> '{n2}'")
    assert n2 == "Amoxicillin"

    # 5. Dose Form Guessing
    df1 = guess_dose_form("Tab. Allegra")
    print(f"guess_dose_form('Tab. Allegra') -> '{df1}'")
    assert df1 == "tablet"

    print("\nâœ… ALL HARDENING TESTS PASSED!")

if __name__ == "__main__":
    try:
        import traceback
        import re
        print(f"Debug: re module is {re}")
        test_hardening()
    except AssertionError as e:
        print(f"\nTEST FAILED")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        traceback.print_exc()
        sys.exit(1)
