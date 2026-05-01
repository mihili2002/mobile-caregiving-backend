from typing import Dict, Any, Tuple
import pandas as pd
import joblib
import os
import io
import re
from pypdf import PdfReader
from app.services.vision_llm import extract_with_openai_vision
from app.services.ocr_fallback import extract_with_ocr_or_pdf
from app.services.ml_inferences import predict_labels
from rapidfuzz import process
from app.services.drug_dictionary import DRUG_DICTIONARY

FREQ_MAP = {
    "od": 1,
    "bd": 2,
    "tds": 3,
    "qid": 4,
}

TIMING_MAP = {
    "ac": "before_meal",
    "pc": "after_meal",
    "hs": "bedtime",
    "nocte": "bedtime"
}

def extract_patterns(text: str):
    """Detects medical shorthand patterns from raw text snippets."""
    text_l = text.lower()

    freq = None
    freq_text = None
    timing = "unknown"
    is_prn = False
    extracted_dose_pattern = None

    # Dose pattern detection (1-0-1, 1-1-1, etc.)
    dp_match = re.search(r"\b(\d)-(\d)-(\d)\b", text_l)
    if dp_match:
        extracted_dose_pattern = f"{dp_match.group(1)}-{dp_match.group(2)}-{dp_match.group(3)}"
        # If we got a dose pattern, we can also calculate a frequency
        calculated_freq = sum(int(x) for x in dp_match.groups())
        if calculated_freq > 0:
            freq = calculated_freq
            freq_text = f"{freq} times daily"

    # Frequency detection (Fallback to defaults if dose pattern missing)
    for key, val in FREQ_MAP.items():
        if re.search(rf"\b{key}\b", text_l):
            if freq is None:
                freq = val
                freq_text = key.upper()
            if not extracted_dose_pattern:
                if key == "od": extracted_dose_pattern = "1-0-0"
                elif key == "bd": extracted_dose_pattern = "1-0-1"
                elif key == "tds": extracted_dose_pattern = "1-1-1"
                elif key == "qid": extracted_dose_pattern = "1-1-1-1"

    # Timing detection
    for key, val in TIMING_MAP.items():
        if re.search(rf"\b{key}\b", text_l):
            timing = val
            # Map timing to pattern if still missing
            if not extracted_dose_pattern:
                if val == "bedtime": extracted_dose_pattern = "0-0-1"
                elif val == "morning": extracted_dose_pattern = "1-0-0"

    # PRN detection
    if re.search(r"\b(prn|sos)\b", text_l):
        is_prn = True

    # Duration detection (x 10 days, x 2 weeks)
    duration = None
    duration_match = re.search(r"(?:x|for)\s*(\d+)\s*(day|days|week|weeks|d|w)", text_l)
    if duration_match:
        num = int(duration_match.group(1))
        unit = duration_match.group(2)
        if unit.startswith("w"):
            duration = num * 7
        else:
            duration = num
            
    return {
        "frequency_per_day": freq,
        "frequency_text": freq_text,
        "timing": timing,
        "is_prn": is_prn,
        "duration_days": duration,
        "dose_pattern": extracted_dose_pattern
    }

def hybrid_enrich_medication(med: dict):
    """Enriches extracted medication with regex patterns and dictionary normalization."""
    raw = med.get("raw_text", "")
    
    # Pre-clean drug name for matching
    d_name = med.get("drug_name", "")
    med["drug_name"] = normalize_drug_name(d_name)

    if not raw:
        return med

    regex_data = extract_patterns(raw)

    # Fill in missing or "unknown" fields from regex data
    for k, v in regex_data.items():
        current_val = med.get(k)
        if current_val in [None, "", "unknown", 0]:
             if v is not None:
                med[k] = v

    return med

def normalize_drug_name(name: str) -> str:
    """Fixes OCR spelling errors using fuzzy matching against the drug dictionary."""
    if not name:
        return name
    
    # Pre-process: strip common noise like brand variants (ventek, etc)
    clean_name = re.sub(r"\s+(ventek|plus|xr|cr|sr|hctz)$", "", name, flags=re.I).strip()
    
    # Fuzzy match with a cutoff score of 70%
    match = process.extractOne(clean_name.lower(), DRUG_DICTIONARY, score_cutoff=70)
    if match:
        return match[0]
    
    return clean_name

def extract_digital_pdf_text(file_bytes: bytes) -> str:
    """Extracts raw text from a searchable PDF."""
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in reader.pages[:2]: # First 2 pages
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        print(f"Digital PDF extraction failed: {e}")
        return ""

def extract_medications(file_bytes: bytes, filename: str, content_type: str) -> Tuple[Dict[str, Any], str]:
    is_pdf = "pdf" in (content_type or "").lower() or filename.lower().endswith(".pdf")
    
    # 1. Pipeline execution
    try:
        data = extract_with_openai_vision(file_bytes, filename, content_type)
        method = "vision_llm"
    except Exception as e:
        print(f"Vision LLM failed, falling back to OCR. Error: {e}")
        data = extract_with_ocr_or_pdf(file_bytes, filename, content_type)
        method = "ocr_fallback"

    meds = data.get("medications", []) or []
    if not meds and method == "vision_llm":
        data = extract_with_ocr_or_pdf(file_bytes, filename, content_type)
        method = "ocr_fallback"
        meds = data.get("medications", []) or []

    # 2. Post-processing: Hybrid Enrichment (Regex + Fuzzy Dictionary)
    enriched_meds = []
    for med in meds:
        enriched_meds.append(hybrid_enrich_medication(med))
    
    data["medications"] = enriched_meds
    return data, method

def label_ocr_lines(lines: list[str]):
    # remove empty/very short lines to reduce noise
    clean = [l.strip() for l in lines if l and len(l.strip()) >= 2]
    if not clean:
        return []
    labels = predict_labels(clean)
    return list(zip(clean, labels))

# --- Feature Preparation Helpers (Restored) ---

def prepare_features(data: Dict[str, Any]) -> pd.DataFrame:
    """Prepares features 5 columns for AI models from a flat dictionary."""
    age = int(data.get('age', 65))
    
    gender_map = {'Male': 0, 'Female': 1, 'Other': 2}
    mobility_map = {'Walking': 0, 'Independent': 0, 'Cane': 1, 'Walker': 1, 'Wheelchair': 2, 'Bedridden': 3, 'Bedbound': 3} 
    cognitive_map = {'Normal': 0, 'Mild Impairment': 1, 'Moderate': 2, 'Severe': 3}
    task_type_map = {'common': 0, 'medication': 1, 'therapist': 2}
    
    gender_val = gender_map.get(data.get('gender', 'Male'), 0)
    mobility_val = mobility_map.get(data.get('mobility_level', 'Walking'), 0)
    cognitive_val = cognitive_map.get(data.get('cognitive_level', 'Normal'), 0)
    
    # Handle task_type which might be 'type' or 'task_type'
    t_type = data.get('type') or data.get('task_type') or 'common'
    task_type_val = task_type_map.get(t_type, 0)
    
    features = pd.DataFrame([[age, gender_val, mobility_val, cognitive_val, task_type_val]], 
                            columns=['Age', 'Gender', 'Mobility', 'Cognitive', 'TaskType'])
    return features

def prepare_features_from_json(profile: Dict[str, Any], task: Dict[str, Any], encoder=None) -> pd.DataFrame:
    """Combines profile and task dicts into features."""
    merged = {**profile, **task}
    return prepare_features(merged)

def prepare_features_from_db(uid: str, encoder, db) -> pd.DataFrame:
    """Fetches profile from DB and prepares features (assuming generic task type)."""
    doc = db.collection('elder_profiles').document(uid).get()
    if not doc.exists:
        # Return default if no profile
        return pd.DataFrame([[65, 0, 0, 0, 0]], columns=['Age', 'Gender', 'Mobility', 'Cognitive', 'TaskType'])
    
    profile = doc.to_dict()
    # Assume generic task type 0 ('common') for generic predictions like reminder strategy
    profile['type'] = 'common'
    return prepare_features(profile)
