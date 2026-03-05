# app/services/meal_planner_llm.py

import os
import json
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

    model = _get_gemini_client()
    response = model.generate_content(prompt)
    text = (response.text or "").strip()

    # Clean accidental code fences
    text = text.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(text)
    except Exception:
        return {"error": "Invalid LLM output", "raw": text}