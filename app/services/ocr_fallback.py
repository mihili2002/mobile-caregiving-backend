import io
import re
from typing import Dict, Any, List
from PIL import Image
import pytesseract
# Windows only: manually point to the executable if not in PATH
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

from pdf2image import convert_from_bytes

SHORTHAND_FREQUENCIES = {
    "od": 1,
    "once daily": 1,
    "bd": 2,
    "bid": 2,
    "twice daily": 2,
    "tds": 3,
    "tid": 3,
    "three times": 3,
    "qid": 4,
    "four times": 4,
}

DOSE_FORM_MAP = {
    "tab": "tablet",
    "cap": "capsule",
    "syp": "syrup",
    "inj": "injection",
    "susp": "suspension",
    "puffs": "inhaler"
}

def guess_timing(text: str):
    t = text.lower()
    if any(re.search(rf"\b{x}\b", t) for x in ["before food", "before meal", "ac", "a.c"]):
        return "before_meal"
    if any(re.search(rf"\b{x}\b", t) for x in ["after food", "after meal", "pc", "p.c"]):
        return "after_meal"
    if any(re.search(rf"\b{x}\b", t) for x in ["with food", "with meal"]):
        return "with_meal"
    if any(re.search(rf"\b{x}\b", t) for x in ["bedtime", "night", "nocte", "hs"]):
        return "bedtime"
    if any(re.search(rf"\b{x}\b", t) for x in ["morning", "mane"]):
        return "morning"
    if any(re.search(rf"\b{x}\b", t) for x in ["afternoon"]):
        return "afternoon"
    if any(re.search(rf"\b{x}\b", t) for x in ["evening"]):
        return "evening"
    if any(re.search(rf"\b{x}\b", t) for x in ["as needed", "sos", "attack", "prn"]):
        return "as_needed"
    return "unknown"

def guess_freq(text: str):
    t = text.lower()
    for shorthand, val in SHORTHAND_FREQUENCIES.items():
        if re.search(rf"\b{shorthand}\b", t):
            return val, shorthand.upper()
    return None, None

def guess_dose_form(text: str):
    t = text.lower()
    for prefix, full in DOSE_FORM_MAP.items():
        if re.search(rf"\b{prefix}\b", t):
            return full
    return None

def normalize_strength(s: str) -> str:
    m = re.search(r"(\d+)\s*(mg|ml|mcg|g|tab|cap|caps)", s.lower())
    if m:
        return f"{m.group(1)} {m.group(2)}"
    return s

def clean_drug_name(name: str) -> str:
    cleaned = re.sub(r"^(tab|cap|syp|inj|susp|tab\.|cap\.|syp\.|inj\.)\s+", "", name, flags=re.I)
    return cleaned.strip()

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
    
    # Try to find a general date
    date_match = re.search(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", raw)
    prescription_date = date_match.group(1) if date_match else None

    for line in lines:
        dose_match = re.search(r"(\d+\s?(mg|ml|mcg|g|tab|cap))", line.lower())
        timing = guess_timing(line)
        freq_val, freq_text = guess_freq(line)
        is_prn = any(x in line.lower() for x in ["sos", "prn", "as needed"])
        dose_form = guess_dose_form(line)

        drug_name = line
        strength = "unknown"
        if dose_match:
            drug_name = line[:dose_match.start()].strip()
            strength = normalize_strength(dose_match.group(1))

        drug_name = clean_drug_name(drug_name)

        if len(drug_name) < 3:
            continue

        meds.append({
            "drug_name": drug_name,
            "strength": strength,
            "dose_pattern": strength, # fallback
            "dose_unit": "unknown",
            "dose_form": dose_form,
            "frequency_per_day": freq_val,
            "frequency_text": freq_text,
            "is_prn": is_prn,
            "timing": timing,
            "meals": None,
            "duration": None,
            "duration_days": None,
            "duration_text": None,
            "from_date": prescription_date,
            "to_date": None,
            "route": "unknown",
            "notes": "OCR fallback (review required)",
            "confidence": 0.4,
            "raw_text": line
        })

    return {"medications": meds, "raw_text": raw}

def extract_with_ocr_or_pdf(file_bytes: bytes, filename: str, content_type: str) -> Dict[str, Any]:
    is_pdf = "pdf" in (content_type or "").lower() or filename.lower().endswith(".pdf")

    if is_pdf:
        # Convert first 1-2 pages
        pages = convert_from_bytes(file_bytes, first_page=1, last_page=2)
        raw_all = []
        for p in pages:
            raw_all.append(_ocr_image(p))
        return _extract_from_text("\n".join(raw_all))

    # image
    img = Image.open(io.BytesIO(file_bytes))
    raw = _ocr_image(img)
    return _extract_from_text(raw)
