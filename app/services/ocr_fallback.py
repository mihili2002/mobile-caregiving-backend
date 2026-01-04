import io
import re
from typing import Dict, Any, List
from PIL import Image
import pytesseract
# Windows only: manually point to the executable if not in PATH
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

from pdf2image import convert_from_bytes

MEAL_WORDS = {
    "breakfast": ["breakfast", "morning"],
    "lunch": ["lunch", "noon", "afternoon"],
    "dinner": ["dinner", "night", "evening"],
}

def guess_timing(text: str):
    t = text.lower()
    if "before food" in t or "before meal" in t or "a.c" in t or " ac " in t:
        return "before_meal"
    if "after food" in t or "after meal" in t or "p.c" in t or " pc " in t:
        return "after_meal"
    if "with food" in t or "with meal" in t:
        return "with_meal"
    return "unknown"

def guess_meals(text: str):
    t = text.lower()
    meals = []
    for meal, words in MEAL_WORDS.items():
        if any(w in t for w in words):
            meals.append(meal)
    return meals or None

def _ocr_image(img: Image.Image) -> str:
    try:
        return pytesseract.image_to_string(img.convert("RGB"))
    except pytesseract.TesseractNotFoundError:
        print("ERROR: Tesseract OCR is not installed or not found at the configured path.")
        return ""
    except Exception as e:
        print(f"ERROR: Tesseract OCR failed: {e}")
        return ""

def _extract_from_text(raw: str) -> Dict[str, Any]:
    if not raw:
        return {"medications": [], "error": "OCR failed or produced no text"}
    
    lines = [l.strip() for l in raw.split("\n") if l.strip()]
    meds: List[dict] = []

    for line in lines:
        dose_match = re.search(r"(\d+\s?(mg|ml|mcg|g))", line.lower())
        timing = guess_timing(line)
        meals = guess_meals(line)

        drug_name = line
        if dose_match:
            drug_name = line[:dose_match.start()].strip()

        if len(drug_name) < 3:
            continue

        meds.append({
            "drug_name": drug_name,
            "dosage": dose_match.group(1) if dose_match else "unknown",
            "frequency": None,
            "timing": timing,
            "meals": meals,
            "duration": None,
            "notes": "OCR fallback extraction (review required)",
            "confidence": 0.45
        })

    return {"medications": meds}

def extract_with_ocr_or_pdf(file_bytes: bytes, filename: str, content_type: str) -> Dict[str, Any]:
    is_pdf = "pdf" in (content_type or "").lower() or filename.lower().endswith(".pdf")

    if is_pdf:
        # Convert first 1-2 pages (tune as needed)
        pages = convert_from_bytes(file_bytes, first_page=1, last_page=2)
        raw_all = []
        for p in pages:
            raw_all.append(_ocr_image(p))
        return _extract_from_text("\n".join(raw_all))

    # image
    img = Image.open(io.BytesIO(file_bytes))
    raw = _ocr_image(img)
    return _extract_from_text(raw)
