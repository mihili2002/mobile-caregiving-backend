# app/services/meal_planner_llm.py
import os
import json
from pathlib import Path

from dotenv import load_dotenv
import google.generativeai as genai


# Load .env from project root reliably (Windows friendly)
# project_root = .../mobile-caregiving-backend
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError(
        "Gemini API key not found. Set GOOGLE_API_KEY (or GEMINI_API_KEY) in .env "
        "or as an environment variable."
    )

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")


def generate_meal_plan(nutrients: dict, foods: list, patient: dict) -> dict:
    foods_text = "\n".join(
        f"- {f.get('Food')} ({f.get('Calories (kcal)')} kcal, {f.get('Protein (g)')}g protein, "
        f"{f.get('Carbohydrate (g)')}g carbs, {f.get('Fat (g)')}g fat)"
        for f in foods
    )

    prompt = f"""
You are a senior clinical dietician. Create a 1-day meal plan for an elderly user.

### Patient Details:
- Age: {patient.get("Age")}
- Gender: {patient.get("Gender")}
- Chronic Disease: {patient.get("Chronic_Disease")}
- Dietary Habits: {patient.get("Dietary_Habits")}
- Allergies: {patient.get("Allergies")}
- Preferred Cuisine: {patient.get("Preferred_Cuisine")}
- Food Aversions: {patient.get("Food_Aversions")}

### Nutrient Targets:
- Calories: {nutrients.get("Recommended_Calories")}
- Protein: {nutrients.get("Recommended_Protein")}
- Carbs: {nutrients.get("Recommended_Carbs")}
- Fats: {nutrients.get("Recommended_Fats")}
- Recommended Meal Plan: {nutrients.get("Recommended_Meal_Plan")}

### Allowed Foods:
{foods_text}

### TASK:
Create a complete 1-day meal plan (Breakfast, Lunch, Dinner, Snacks).
Only use allowed foods.
Return STRICT JSON ONLY:

{{
  "day": 1,
  "meals": {{
    "breakfast": [{{"food_name": "...", "portion": "...", "notes": "..."}}],
    "lunch": [{{"food_name": "...", "portion": "...", "notes": "..."}}],
    "dinner": [{{"food_name": "...", "portion": "...", "notes": "..."}}],
    "snacks": [{{"food_name": "...", "portion": "...", "notes": "..."}}]
  }}
}}
"""

    response = model.generate_content(prompt)
    text = (response.text or "").strip().replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(text)
    except Exception:
        return {"error": "Invalid LLM output", "raw": text}
