# app/services/meal_plan_pipeline.py

from app.services import ml_inference
from app.services.food_filter import get_food_recommendations
from app.services.meal_planner_llm import generate_weekly_meal_plan


def enforce_macro_safety(nutrients: dict) -> tuple[dict, list]:
    """
    Safety post-processing so macro targets are consistent with meal plan type.
    Returns updated nutrients and warnings.
    """
    warnings = []

    calories = float(nutrients.get("Recommended_Calories") or 0)
    fats = float(nutrients.get("Recommended_Fats") or 0)
    meal_plan = (nutrients.get("Recommended_Meal_Plan") or "").lower()

    # ✅ If model says "low-fat", enforce <= 30% calories from fat
    if calories > 0 and "low-fat" in meal_plan:
        max_fat = round((calories * 0.30) / 9, 2)  # 30% calories from fat
        if fats > max_fat:
            warnings.append(
                f"Fat target ({fats}g) exceeded low-fat threshold ({max_fat}g). Adjusted for safety."
            )
            nutrients["Recommended_Fats"] = max_fat

    return nutrients, warnings


def build_meal_plan(patient: dict) -> dict:
    """
    Brain 1 -> Brain 2 -> Brain 3 pipeline:
    1) ML nutrient prediction
    2) Filter foods from dataset
    3) Generate WEEKLY meal plan using Gemini LLM
    """

    # -------------------------------
    # Brain 1: ML prediction
    # -------------------------------
    nutrients = ml_inference.predict_nutrition(patient)

    # ✅ Safety enforcement
    nutrients, warnings = enforce_macro_safety(nutrients)

    # -------------------------------
    # Brain 2: Food filtering
    # -------------------------------
    try:
        foods = get_food_recommendations(patient, nutrients, max_items=30)
    except Exception as e:
        foods = []
        warnings.append(f"Food filtering failed: {str(e)}")

    # -------------------------------
    # Brain 3: WEEKLY LLM meal generation
    # -------------------------------
    try:
        weekly_meal_plan = generate_weekly_meal_plan(nutrients, foods, patient)
    except Exception as e:
        weekly_meal_plan = {
            "error": "LLM weekly meal plan generation failed",
            "details": str(e),
        }
        warnings.append("LLM weekly meal plan generation failed")

    return {
        "nutrient_targets": nutrients,
        "food_options": foods,
        "weekly_meal_plan": weekly_meal_plan,
        "warnings": warnings,
    }
