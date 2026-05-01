from ai.extractor import label_ocr_lines
import sys
import os

# Add parent directory to sys.path to allow imports from caregiving_backend
sys.path.append(os.getcwd())

def test():
    test_lines = [
        "Paracetamol 500mg",
        "Take 1 tablet daily",
        "Morning",
        "", # Should be filtered
        "A", # Should be filtered (too short)
        "Hospital General",
        "Patient: John Doe"
    ]
    
    print("Testing label_ocr_lines...")
    try:
        results = label_ocr_lines(test_lines)
        for line, label in results:
            print(f"Line: '{line}' -> Label: '{label}'")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test()
