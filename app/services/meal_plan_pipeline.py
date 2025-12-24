from app.services import ml_inference
from app.services.food_filter import get_food_recommendations
from app.services.meal_planner_llm import generate_meal_plan


def build_meal_plan(patient: dict) -> dict:
    nutrients = ml_inference.predict_nutrition(patient)
    foods = get_food_recommendations(patient, nutrients)
    meal_plan = generate_meal_plan(nutrients, foods, patient)

    return {
        "nutrient_targets": nutrients,
        "food_options": foods,
        "meal_plan": meal_plan
    }
