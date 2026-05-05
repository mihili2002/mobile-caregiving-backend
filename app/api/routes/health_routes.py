import os
import json
import re
import traceback
from typing import Any, Dict

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException

from app.api.deps import require_role

try:
    import google.generativeai as genai  # type: ignore
except Exception:
    genai = None  # type: ignore

# Configure Gemini if key present
_GEMINI_KEY = os.getenv("GEMINI_API_KEY")
if genai and _GEMINI_KEY:
    try:
        genai.configure(api_key=_GEMINI_KEY)
    except Exception:
        # don't crash import-time if config fails; we'll surface on call
        pass

router = APIRouter(prefix="/api/health", tags=["health"])


def _ensure_json_text(raw: str) -> str:
    """
    Cleaner extraction that handles markdown fences and 
    common LLM conversational 'noise'.
    """
    # 1. Remove Markdown code blocks first
    cleaned = re.sub(r"```json\s?|```", "", raw).strip()
    
    # 2. Use a non-greedy search to find the JSON object
    # This looks for the first '{' and the last '}' in the string
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    
    if match:
        json_candidate = match.group(0)
        # 3. Final safety check: can it actually be parsed?
        try:
            json.loads(json_candidate)
            return json_candidate
        except json.JSONDecodeError:
            # If it failed, maybe there was text after the final }
            # Let's try to find the last occurrence of }
            last_bracket = json_candidate.rfind('}')
            if last_bracket != -1:
                return json_candidate[:last_bracket + 1]
    
    return cleaned


def _sanitize(extracted: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure the returned dict contains keys expected by the frontend and types or nulls."""
    def as_int(v):
        try:
            return int(v)
        except Exception:
            return None

    def as_float(v):
        try:
            return float(v)
        except Exception:
            return None

    out = {
        "age": as_int(extracted.get("age")),
        "gender": (extracted.get("gender") if extracted.get("gender") in ("Male", "Female") else None),
        "height_cm": as_float(extracted.get("height_cm")),
        "weight_kg": as_float(extracted.get("weight_kg")),
        "blood_pressure": {
            "systolic": as_int((extracted.get("blood_pressure") or {}).get("systolic") if isinstance(extracted.get("blood_pressure"), dict) else None),
            "diastolic": as_int((extracted.get("blood_pressure") or {}).get("diastolic") if isinstance(extracted.get("blood_pressure"), dict) else None),
        },
        "chronic_conditions": (list(extracted.get("chronic_conditions")) if isinstance(extracted.get("chronic_conditions"), list) else None),
        "blood_sugar_mg_dl": as_float(extracted.get("blood_sugar_mg_dl")),
        "cholesterol_mg_dl": as_float(extracted.get("cholesterol_mg_dl")),
        "dietary_habit": extracted.get("dietary_habit"),
        "preferred_cuisine": extracted.get("preferred_cuisine"),
        "food_allergies": extracted.get("food_allergies"),
        "caloric_intake": as_float(extracted.get("caloric_intake")),
        "protein_intake": as_float(extracted.get("protein_intake")),
        "carbohydrate_intake": as_float(extracted.get("carbohydrate_intake")),
        "fat_intake": as_float(extracted.get("fat_intake")),
    }

    # Normalize empty lists/strings to None
    if out["chronic_conditions"] == []:
        out["chronic_conditions"] = None

    return out


@router.post("/extract-pdf")
async def extract_pdf(file: UploadFile = File(...), user=Depends(require_role(["caregiver", "doctor"]))):
    """Accept a PDF upload, call Gemini to extract patient fields and return JSON.

    Protected: only `caregiver` or `doctor` roles may call this.
    """
    if not genai:
        raise HTTPException(status_code=500, detail="GenAI library not available on server")

    try:
        pdf_bytes = await file.read()
        if not pdf_bytes:
            raise HTTPException(status_code=400, detail="Empty file")

        prompt = """
            Analyze this medical report PDF. Extract the patient information and return it
            ONLY as a valid JSON object. Do not include markdown or explanations.

            Use these exact keys:
            - age (int)
            - gender (string: "Male" or "Female")
            - height_cm (float)
            - weight_kg (float)
            - blood_pressure: { "systolic": int, "diastolic": int }
            - chronic_conditions (list of strings)

            IMPORTANT:
            For chronic_conditions, use ONLY these exact values:
            ["Diabetes", "Hypertension", "Heart Disease"]

            Rules:
            - If the report says "High Blood Pressure", return "Hypertension".
            - If the report says "BP", "high BP", or "blood pressure problem", return "Hypertension".
            - If the report says "Heart condition", "Cardiac disease", or similar, return "Heart Disease".
            - If the report says "No chronic conditions" or "None", return [].
            - Do not return "None" inside chronic_conditions.
            - Do not return any value outside the allowed list.

            Other keys:
            - blood_sugar_mg_dl (float)
            - cholesterol_mg_dl (float)
            - dietary_habit (string: "Vegetarian", "Vegan", "Non-Vegetarian")
            - preferred_cuisine (string)
            - food_allergies (string)
            - caloric_intake (float)
            - protein_intake (float)
            - carbohydrate_intake (float)
            - fat_intake (float)

            If a field is not found, set it to null.
            """

        model = genai.GenerativeModel("gemini-2.5-flash")

        response = model.generate_content([
            prompt,
            {"mime_type": "application/pdf", "data": pdf_bytes},
        ])

        raw = getattr(response, "text", None) or str(response)
        json_text = _ensure_json_text(raw)

        try:
            extracted = json.loads(json_text)
        except Exception as e:
            # Return a helpful error with snippet for debugging
            raise HTTPException(status_code=500, detail=f"Failed to parse JSON from model output: {e}; output snippet: {json_text[:1000]}")

        sanitized = _sanitize(extracted)
        return sanitized

    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc))
