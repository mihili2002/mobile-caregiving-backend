# app/services/meal_plan_pipeline.py

from app.services import ml_inference
from app.services.food_filter import get_food_recommendations
from app.services.meal_planner_llm import generate_weekly_meal_plan
from typing import Tuple, Dict, Any, List


def enforce_macro_safety(nutrients: dict) -> Tuple[dict, List[str]]:
    """
    Safety post-processing so macro targets are consistent with meal plan type.
    Returns updated nutrients and warnings.
    """
    warnings: List[str] = []

    calories = float(nutrients.get("Recommended_Calories") or 0)
    fats = float(nutrients.get("Recommended_Fats") or 0)
    meal_plan = (nutrients.get("Recommended_Meal_Plan") or "").lower()

    # If model says "low-fat", enforce <= 30% calories from fat
    if calories > 0 and "low-fat" in meal_plan:
        max_fat = round((calories * 0.30) / 9, 2)  # 30% calories from fat
        if fats > max_fat:
            warnings.append(
                f"Fat target ({fats}g) exceeded low-fat threshold ({max_fat}g). Adjusted for safety."
            )
            nutrients["Recommended_Fats"] = max_fat

    return nutrients, warnings


def _coerce_week_and_notes(weekly_meal_plan: Any, warnings: List[str]) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[str]]:
    """
    Defensive normalization of the LLM output.
    Ensures we always return a week_list (list) and dietitian_notes (dict).
    Appends parse warnings to the provided warnings list and returns them.
    """
    week_list: List[Dict[str, Any]] = []
    dietitian_notes: Dict[str, Any] = {}

    if isinstance(weekly_meal_plan, dict):
        # try common keys for week
        week_candidates = [
            weekly_meal_plan.get("week"),
            weekly_meal_plan.get("Week"),
            weekly_meal_plan.get("week_list"),
            weekly_meal_plan.get("weekly"),
            weekly_meal_plan.get("week_days"),
            weekly_meal_plan.get("weekdays"),
            # some LLM outputs might nest: {"weekly_meal_plan": {"week": [...]}}
            (weekly_meal_plan.get("weekly_meal_plan") or {}).get("week") if isinstance(weekly_meal_plan.get("weekly_meal_plan"), dict) else None,
            weekly_meal_plan.get("weekDays") if "weekDays" in weekly_meal_plan else None,
        ]

        # pick the first non-empty candidate
        for candidate in week_candidates:
            if candidate is not None:
                week_list = candidate
                break

        # If still none, try to find a nested structure
        if week_list is None:
            week_list = []

        # Normalize dietitian notes
        notes = None
        for nk in ("dietitian_notes", "dietitianNotes", "dietitian", "notes", "dietitian_note"):
            if nk in weekly_meal_plan and weekly_meal_plan[nk] is not None:
                notes = weekly_meal_plan[nk]
                break

        if isinstance(notes, dict):
            dietitian_notes = notes
        elif isinstance(notes, str):
            dietitian_notes = {"text": notes}
            warnings.append("Wrapped string dietitian_notes into dict {'text':...}.")
        elif notes is None:
            dietitian_notes = {}
        else:
            # unknown type
            dietitian_notes = {}
            warnings.append(f"dietitian_notes present but had unexpected type {type(notes)}; coerced to empty dict.")
    else:
        # Not a dict at all
        warnings.append(f"LLM returned non-dict weekly_meal_plan (type={type(weekly_meal_plan)}). Coerced to empty week and notes.")

    # Ensure week_list is a list
    if not isinstance(week_list, list):
        # If week_list is a dict with numeric keys, try to convert
        if isinstance(week_list, dict):
            # try sorting by key if numeric-like
            try:
                items = []
                for k, v in week_list.items():
                    # attempt to find day number
                    items.append(v)
                week_list = items
                warnings.append("Coerced dict->list for week_list.")
            except Exception:
                week_list = []
                warnings.append("LLM returned 'week' with unsupported type; coerced to empty list.")
        else:
            week_list = []
            warnings.append("LLM returned 'week' with unsupported type; coerced to empty list.")

    return week_list, dietitian_notes, warnings


def build_meal_plan(patient: dict) -> dict:
    """
    Brain 1 -> Brain 2 -> Brain 3 pipeline:
    1) ML nutrient prediction
    2) Filter foods from dataset
    3) Generate WEEKLY meal plan using Gemini LLM

    Returns a dict containing:
      - nutrient_targets
      - food_options
      - week (coerced list)
      - dietitian_notes (dict)
      - warnings (list)
      - weekly_meal_plan (raw LLM result, if available)
    """

    # -------------------------------
    # Brain 1: ML prediction
    # -------------------------------
    nutrients = ml_inference.predict_nutrition(patient)

    # Safety enforcement
    nutrients, warnings = enforce_macro_safety(nutrients)

    # -------------------------------
    # Brain 2: Food filtering
    # -------------------------------
    try:
        foods = get_food_recommendations(patient, nutrients, max_items=30)

        print("================================")
        print("FOODS SENT TO LLM:", len(foods))
        for f in foods[:5]:
            print("Food sample:", f)
        print("================================")

        for i, food in enumerate(foods, start=1):
            print(f"{i}. {food}")
    except Exception as e:
        foods = []
        warnings.append(f"Food filtering failed: {str(e)}")

    # -------------------------------
    # Brain 3: WEEKLY LLM meal generation
    # -------------------------------
    try:
        weekly_meal_plan = generate_weekly_meal_plan(nutrients, foods, patient)
        print("RAW LLM OUTPUT:", weekly_meal_plan)
    except Exception as e:
        weekly_meal_plan = {
            "error": "LLM weekly meal plan generation failed",
            "details": str(e),
        }
        warnings.append("LLM weekly meal plan generation failed")

        print("================================")
        print("FOODS SENT TO LLM:", len(foods))
        print("LLM RESPONSE (exception):", weekly_meal_plan)
        print("================================")

    # Defensive: ensure week exists and is a list, extract dietitian_notes
    week_list, dietitian_notes, warnings = _coerce_week_and_notes(weekly_meal_plan, warnings)

    # Debug log (will help debug in logs)
    try:
        print("=== LLM WEEK LENGTH ===", len(week_list))
    except Exception:
        print("=== LLM WEEK LENGTH === (unknown)")

    try:
        print("=== LLM DIETITIAN NOTES (keys) ===", list(dietitian_notes.keys()) if isinstance(dietitian_notes, dict) else type(dietitian_notes))
    except Exception:
        print("=== LLM DIETITIAN NOTES === (unprintable)")

    # If week_list empty, add explanatory warning
    if not week_list:
        warnings.append("LLM returned no usable 'week' data; empty week saved. Inspect 'weekly_meal_plan' in returned object for raw output.")

    # Build normalized return object
    result = {
        "nutrient_targets": nutrients,
        "food_options": foods,
        "week": week_list,
        "dietitian_notes": dietitian_notes,
        "warnings": warnings,
        # Keep raw LLM content for debugging / persistence upstream
        "weekly_meal_plan": weekly_meal_plan,
    }

    return result