# app/services/meal_planner_llm.py
 
import os
import json
import re
from pathlib import Path
from typing import Dict, List, Any
 
from dotenv import load_dotenv
 
try:
    import google.generativeai as genai
except ImportError:
    genai = None
 
 
# -------------------------------------------------------
# Load .env reliably from project root
# -------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")
 
 
def _get_gemini_client():
    """
    Lazily create Gemini client.
    This prevents your app from crashing on startup if key is missing.
    """
    if genai is None:
        raise RuntimeError(
            "google.generativeai is not installed. Install it with: pip install google-generativeai"
        )
 
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Gemini API key not found. Set GOOGLE_API_KEY (or GEMINI_API_KEY) in .env "
            "or as an environment variable."
        )
 
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("gemini-2.5-flash")
 
 
def _extract_json_from_text(text: str) -> Dict[str, Any]:
    """
    Robustly extract a JSON object from LLM free-text output.
 
    Strategy:
    - Strip common fences (```json, ```).
    - Find first "{" and last "}" and attempt to parse that substring.
    - If that fails, attempt to find the largest {...} substring using regex heuristics.
    - If parsing still fails, raise JSONDecodeError or ValueError with context.
    """
    original = text
    # Remove common markdown/code fences
    text = text.replace("```json", "").replace("```", "").strip()
 
    # Quick attempt: find first { and last }
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and last > first:
        candidate = text[first : last + 1]
        try:
            parsed = json.loads(candidate)
            return parsed
        except json.JSONDecodeError:
            # fall through to regex attempts
            pass
 
    # Regex attempt: non-greedy find top-level JSON-like braces blocks
    # This will try to find the largest balanced JSON-like substring.
    # We attempt several candidates and try to parse them (largest-first).
    brace_positions = [m.start() for m in re.finditer(r"\{", text)]
    end_positions = [m.start() for m in re.finditer(r"\}", text)]
 
    # Generate candidate substrings by pairing a start with the last end after it
    candidates = []
    for s in brace_positions:
        # find the last '}' after s
        ends_after = [e for e in end_positions if e > s]
        if not ends_after:
            continue
        e = ends_after[-1]
        candidates.append(text[s : e + 1])
 
    # sort candidates by length descending (prefer larger JSON objects)
    candidates = sorted(set(candidates), key=len, reverse=True)
 
    for cand in candidates:
        try:
            parsed = json.loads(cand)
            return parsed
        except json.JSONDecodeError:
            continue
 
    # Final fallback: try to parse entire cleaned text
    try:
        parsed = json.loads(text)
        return parsed
    except json.JSONDecodeError as je:
        # Raise with helpful context
        raise json.JSONDecodeError(
            f"Failed to extract JSON from LLM output. Last attempt text length={len(text)}",
            doc=text,
            pos=0,
        ) from je
 
 
def _normalize_parsed_week(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure the parsed dict has a 'week' key (list) and 'dietitian_notes' (dict).
    Accept several alternative keys and normalize them. Returns the normalized dict.
    Adds lightweight 'parse_warnings' list on the returned dict when we coerce things.
    """
    warnings: List[str] = []
 
    # Normalize week key from common alternatives
    week_keys = ["week", "Week", "week_list", "weekly", "week_days", "weekdays", "weekly_meal_plan"]
    week_value = None
    for k in week_keys:
        if k in parsed and parsed[k] is not None:
            week_value = parsed[k]
            # If the actual structure is nested like {'weekly_meal_plan': {'week': [...]}}
            if k == "weekly_meal_plan" and isinstance(week_value, dict) and "week" in week_value:
                week_value = week_value["week"]
            # keep the first hit
            break
 
    if week_value is None:
        # No week found — we will not throw here, but return an explanatory error structure
        warnings.append("No 'week' key found in LLM parsed JSON.")
        parsed["week"] = []
    else:
        # Coerce to list if possible
        if isinstance(week_value, list):
            parsed["week"] = week_value
        else:
            # If it's a dict or other, try to wrap or extract
            if isinstance(week_value, dict) and "week" in week_value and isinstance(week_value["week"], list):
                parsed["week"] = week_value["week"]
                warnings.append("Coerced nested 'week' from dict -> list")
            else:
                # Not a list — coerce to empty and warn
                warnings.append(f"'week' found but not a list (type={type(week_value)}). Coerced to empty list.")
                parsed["week"] = []
 
    # Normalize dietitian_notes
    notes_keys = ["dietitian_notes", "dietitianNotes", "dietitian", "notes", "dietitian_note"]
    notes_value = {}
    for k in notes_keys:
        if k in parsed and parsed[k] is not None:
            notes_value = parsed[k]
            break
 
    if not isinstance(notes_value, dict):
        # if notes_value is string, wrap it
        if isinstance(notes_value, str) and notes_value.strip():
            notes_value = {"text": notes_value}
            warnings.append("Wrapped string dietitian_notes into dict {'text': ...}")
        else:
            notes_value = {}
 
    parsed["dietitian_notes"] = notes_value
 
    if warnings:
        parsed["parse_warnings"] = warnings
 
    return parsed
 
 
def generate_weekly_meal_plan(
    nutrients: Dict[str, Any],
    foods: List[Dict[str, Any]],
    patient: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Brain 3: LLM meal plan generation for 7 days (weekly)
    """
 
    # If food list is empty - return safe response
    if not foods:
        return {
            "error": "No foods available after filtering",
            "week": []
        }
 
    foods_text = "\n".join(
        f"- {f.get('Food')} ({f.get('Calories (kcal)')} kcal, "
        f"{f.get('Carbohydrate (g)')}g carbs, {f.get('Protein (g)')}g protein, {f.get('Fat (g)')}g fat)"
        for f in foods
    )
 
    prompt = f"""
You are a senior clinical dietician.
 
Create a **7-day weekly meal plan** for an elderly user.
 
IMPORTANT RULES:
- ONLY use foods from the Allowed Foods list.
- DO NOT include foods not listed.
- Use simple, elder-friendly portions (NO decimals like 0.75 serving).
- Portion must be in grams/ml or household measures:
  e.g. "150g", "250ml", "1 bowl", "2 string hoppers", "1 slice", "1 cup".
- Must respect allergies and aversions.
- Keep plan mild (non-spicy) when aversion is spicy.
- For hypertension/heart disease: prefer low-oil, low-sodium preparation notes.
- Return STRICT JSON ONLY. No markdown.
 
### Patient Details:
- Age: {patient.get("age")}
- Gender: {patient.get("gender")}
- Chronic Disease: {", ".join(patient.get("chronic_conditions", []))}
- Dietary Habits: {patient.get("dietary_habit")}
- Allergies: {patient.get("food_allergies")}
- Preferred Cuisine: {patient.get("preferred_cuisine")}
- Food Aversions: {patient.get("food_aversions")}
 
### DAILY Nutrient Targets (approx):
- Calories: {nutrients.get("Recommended_Calories")}
- Protein: {nutrients.get("Recommended_Protein")}
- Carbs: {nutrients.get("Recommended_Carbs")}
- Fats: {nutrients.get("Recommended_Fats")}
- Recommended Meal Plan: {nutrients.get("Recommended_Meal_Plan")}
 
### Allowed Foods:
{foods_text}
 
### OUTPUT FORMAT (STRICT JSON):
{{
  "week": [
    {{
      "day": 1,
      "meals": {{
        "breakfast": [{{"food_name": "...", "portion": "150g", "notes": "..."}}],
        "lunch": [{{"food_name": "...", "portion": "1 bowl", "notes": "..."}}],
        "dinner": [{{"food_name": "...", "portion": "2 string hoppers", "notes": "..."}}],
        "snacks": [{{"food_name": "...", "portion": "1 cup", "notes": "..."}}]
      }}
    }},
    {{
      "day": 2,
      "meals": {{
        "breakfast": [],
        "lunch": [],
        "dinner": [],
        "snacks": []
      }}
    }},
    {{
      "day": 3,
      "meals": {{
        "breakfast": [],
        "lunch": [],
        "dinner": [],
        "snacks": []
      }}
    }},
    {{
      "day": 4,
      "meals": {{
        "breakfast": [],
        "lunch": [],
        "dinner": [],
        "snacks": []
      }}
    }},
    {{
      "day": 5,
      "meals": {{
        "breakfast": [],
        "lunch": [],
        "dinner": [],
        "snacks": []
      }}
    }},
    {{
      "day": 6,
      "meals": {{
        "breakfast": [],
        "lunch": [],
        "dinner": [],
        "snacks": []
      }}
    }},
    {{
      "day": 7,
      "meals": {{
        "breakfast": [],
        "lunch": [],
        "dinner": [],
        "snacks": []
      }}
    }}
  ],
  "dietitian_notes": {{
    "macro_alignment": "brief explanation of how close macros are",
    "chronic_disease_safety": "brief explanation",
    "allergy_safety": "brief explanation"
  }}
}}
"""
 
    # Generate content from Gemini
    try:
        model = _get_gemini_client()
        response = model.generate_content(prompt)
        text = (response.text or "").strip()
    except Exception as e:
        # If LLM call fails, return a structured error that pipeline can log and persist
        return {
            "error": "LLM call failed",
            "details": str(e),
            "week": []
        }
 
    # Debug logging: capture raw LLM output for easier debugging
    print("===== LLM RAW OUTPUT START =====")
    print(text[:800])  # print up to first 800 chars to avoid flooding logs
    print("===== LLM RAW OUTPUT END =====")
 
    # Attempt robust JSON extraction & normalization
    try:
        parsed = _extract_json_from_text(text)
    except json.JSONDecodeError as je:
        # Return structured error with raw text and decode error message
        print("LLM JSON decode error:", repr(je))
        return {"error": "Invalid LLM JSON", "raw": text, "json_error": str(je), "week": []}
    except Exception as e:
        print("LLM parse exception:", repr(e))
        return {"error": "Failed to extract JSON from LLM output", "raw": text, "parse_error": str(e), "week": []}
 
    # Normalize keys and ensure 'week' + 'dietitian_notes' exist and are well-typed
    normalized = _normalize_parsed_week(parsed)
 
    # Final sanity checks and helpful debug prints
    week_list = normalized.get("week", [])
    notes = normalized.get("dietitian_notes", {})
 
    print("=== Parsed week length ===", len(week_list))
    # Print a small sample of first day's structure if present
    if week_list and isinstance(week_list, list):
        try:
            sample0 = week_list[0]
            print("=== Week[0] sample keys ===", list(sample0.keys()) if isinstance(sample0, dict) else type(sample0))
        except Exception:
            pass
 
    # If 'week' is empty, include a helpful message inside returned dict
    if not isinstance(week_list, list) or len(week_list) == 0:
        # keep dietitian notes if present
        ret = {
            "error": "LLM returned no usable 'week' data",
            "raw_parsed": parsed,
            "dietitian_notes": notes,
            "week": [],
        }
        # Include parse_warnings if any
        if "parse_warnings" in normalized:
            ret["parse_warnings"] = normalized["parse_warnings"]
        print("LLM produced empty week; returning error wrapper.")
        return ret
 
    # Otherwise return the normalized parsed object (safe shape)
    # Ensure we only return JSON-serializable stuff
    try:
        return {
            "week": week_list,
            "dietitian_notes": notes if isinstance(notes, dict) else {"text": str(notes)},
            **({k: normalized[k] for k in normalized if k not in ("week", "dietitian_notes")} if isinstance(normalized, dict) else {})
        }
    except Exception:
        # As a last fallback, return minimal safe structure
        return {"week": week_list, "dietitian_notes": notes}