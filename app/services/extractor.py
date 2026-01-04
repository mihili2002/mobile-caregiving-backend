from typing import Dict, Any, Tuple
import pandas as pd
import joblib
import os
from app.services.vision_llm import extract_with_openai_vision
from app.services.ocr_fallback import extract_with_ocr_or_pdf
from app.services.ml_inference import predict_labels

# Load MH Encoder
try:
    mh_encoder = joblib.load(os.path.join('ml', 'models', 'mh_mlb.joblib'))
except:
    print("Warning: mh_mlb.joblib not found. Mental health features might fail.")
    mh_encoder = None

def extract_medications(file_bytes: bytes, filename: str, content_type: str) -> Tuple[Dict[str, Any], str]:
    # Vision first
    try:
        data = extract_with_openai_vision(file_bytes, filename, content_type)
        meds = data.get("medications", []) or []
    except Exception as e:
        print(f"Vision LLM failed, falling back to OCR. Error: {e}")
        return extract_with_ocr_or_pdf(file_bytes, filename, content_type), "ocr_fallback"

    # If nothing extracted, fallback
    if not meds:
        return extract_with_ocr_or_pdf(file_bytes, filename, content_type), "ocr_fallback"

    return data, "vision_llm"

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
