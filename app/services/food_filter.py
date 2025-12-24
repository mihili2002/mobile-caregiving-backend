import pandas as pd
import re
from functools import lru_cache
from pathlib import Path

FOOD_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "food_database_final.csv"


# ---------------- Helpers ---------------- #

def clean_number(value):
    if pd.isna(value):
        return 0.0
    match = re.findall(r"[\d\.]+", str(value))
    return float(match[0]) if match else 0.0


def parse_list(text: str):
    if not text:
        return []
    parts = re.split(r"[;,/]", str(text))
    return [p.strip().lower() for p in parts if p.strip()]


# ---------------- Load DB ---------------- #

@lru_cache(maxsize=1)
def load_food_db() -> pd.DataFrame:
    df = pd.read_csv(FOOD_DB_PATH)

    for col in ["Calories (kcal)", "Protein (g)", "Carbohydrate (g)", "Fat (g)"]:
        if col in df.columns:
            df[col] = df[col].apply(clean_number)

    return df.fillna(0)


# ---------------- Main API ---------------- #

def get_food_recommendations(patient: dict, targets: dict, max_items=20):
    df = load_food_db().copy()

    dietary = patient.get("dietary_habits", "").lower()
    disease = patient.get("chronic_disease", "").lower()
    meal_plan = targets.get("Recommended_Meal_Plan", "").lower()

    if "vegetarian" in dietary and "Vegetarian" in df:
        df = df[df["Vegetarian"] == "Yes"]

    if "diabetes" in disease and "Diabetic_Friendly" in df:
        df = df[df["Diabetic_Friendly"] == "Yes"]

    if "low-fat" in meal_plan and "Low_Fat" in df:
        df = df[df["Low_Fat"] == "Yes"]

    # allergies
    for term in parse_list(patient.get("allergies")):
        df = df[~df["Food"].str.lower().str.contains(term)]

    # macro matching
    per_meal_cal = targets["Recommended_Calories"] / 3
    per_meal_prot = targets["Recommended_Protein"] / 3

    df = df[
        (df["Calories (kcal)"].between(per_meal_cal * 0.6, per_meal_cal * 1.4)) &
        (df["Protein (g)"].between(per_meal_prot * 0.4, per_meal_prot * 1.6))
    ]

    df["score"] = (
        (df["Calories (kcal)"] - per_meal_cal).abs() * 0.7 +
        (df["Protein (g)"] - per_meal_prot).abs() * 0.3
    )

    return df.sort_values("score").head(max_items).to_dict(orient="records")
