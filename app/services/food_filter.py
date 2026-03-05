import pandas as pd
import re
import random
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Any


# -------------------------------------------------
# Path to food database
# -------------------------------------------------
FOOD_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "food_database_final.csv"


# -------------------------------------------------
# Helpers
# -------------------------------------------------
def clean_number(value) -> float:
    """Convert values like '80g', '110 kcal' → float"""
    if pd.isna(value):
        return 0.0
    value = str(value).lower().strip()
    match = re.findall(r"[\d\.]+", value)
    return float(match[0]) if match else 0.0


def parse_list(text: str) -> List[str]:
    """Convert 'nuts, egg' → ['nuts', 'egg']"""
    if not text:
        return []
    text = str(text).strip().lower()
    if text in ["none", "no", "n/a", "nil", "-"]:
        return []
    parts = re.split(r"[;,/]", text)
    return [p.strip() for p in parts if p.strip()]


# -------------------------------------------------
# Load DB (cached)
# -------------------------------------------------
@lru_cache(maxsize=1)
def load_food_db() -> pd.DataFrame:
    df = pd.read_csv(FOOD_DB_PATH)

    numeric_cols = [
        "Quantity",
        "Calories (kcal)",
        "Carbohydrate (g)",
        "Protein (g)",
        "Fat (g)",
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = df[col].apply(clean_number)

    df = df.fillna(0)

    if "Food" in df.columns:
        df["Food"] = df["Food"].astype(str)

    return df


# -------------------------------------------------
# Main API
# -------------------------------------------------
def get_food_recommendations(
    patient: Dict[str, Any],
    targets: Dict[str, float],
    max_items: int = 30,
):
    """
    Returns a DIVERSE list of food options matching nutrition targets.
    """

    df = load_food_db().copy()

    # -------------------------------------------------
    # Patient attributes
    # -------------------------------------------------
    disease = str(patient.get("Chronic_Disease", "")).lower()
    dietary = str(patient.get("Dietary_Habits", "")).lower()
    meal_plan = str(targets.get("Recommended_Meal_Plan", "")).lower()

    allergies = parse_list(patient.get("Allergies", ""))
    aversions = parse_list(patient.get("Food_Aversions", ""))

    # -------------------------------------------------
    # A) Dietary filters (SOFT)
    # -------------------------------------------------
    if "vegetarian" in dietary and "Vegetarian" in df.columns:
        df = df[df["Vegetarian"].astype(str).str.lower() == "yes"]

    if "vegan" in dietary and "Vegan" in df.columns:
        df = df[df["Vegan"].astype(str).str.lower() == "yes"]

    # -------------------------------------------------
    # B) Disease filters (ONLY if applicable)
    # -------------------------------------------------
    if "diabetes" in disease and "Diabetic_Friendly" in df.columns:
        df = df[df["Diabetic_Friendly"].astype(str).str.lower() == "yes"]

    if ("low fat" in meal_plan or "low-fat" in meal_plan) and "Low_Fat" in df.columns:
        df = df[df["Low_Fat"].astype(str).str.lower() == "yes"]

    if "low carb" in meal_plan and "Low_Carb" in df.columns:
        df = df[df["Low_Carb"].astype(str).str.lower() == "yes"]

    if "high protein" in meal_plan and "High_Protein" in df.columns:
        df = df[df["High_Protein"].astype(str).str.lower() == "yes"]

    # -------------------------------------------------
    # C) Allergy filtering (STRICT for safety)
    # -------------------------------------------------
    for a in allergies:
        df = df[~df["Food"].str.lower().str.contains(a, na=False)]

    if any("nut" in a or "peanut" in a for a in allergies):
        nut_words = [
            "nut", "peanut", "almond", "cashew",
            "walnut", "pistachio", "hazelnut"
        ]
        for n in nut_words:
            df = df[~df["Food"].str.lower().str.contains(n, na=False)]

    if any("lactose" in a or "milk" in a for a in allergies):
        dairy = ["milk", "cheese", "butter", "cream", "yogurt", "curd"]
        for d in dairy:
            df = df[~df["Food"].str.lower().str.contains(d, na=False)]

    # -------------------------------------------------
    # D) Food aversions
    # -------------------------------------------------
    if any("spicy" in a for a in aversions):
        spicy_words = ["chili", "miris", "spicy", "hot"]
        for s in spicy_words:
            df = df[~df["Food"].str.lower().str.contains(s, na=False)]

    # -------------------------------------------------
    # E) SOFT MACRO SCORING (NO HARD CUTS)
    # -------------------------------------------------
    total_cal = float(targets.get("Recommended_Calories", 1800))
    total_prot = float(targets.get("Recommended_Protein", 60))
    total_carbs = float(targets.get("Recommended_Carbs", 200))
    total_fat = float(targets.get("Recommended_Fats", 60))

    per_meal_cal = total_cal / 3
    per_meal_prot = total_prot / 3
    per_meal_carbs = total_carbs / 3
    per_meal_fat = total_fat / 3

    df["cal_diff"] = abs(df["Calories (kcal)"] - per_meal_cal) / per_meal_cal
    df["prot_diff"] = abs(df["Protein (g)"] - per_meal_prot) / per_meal_prot
    df["carb_diff"] = abs(df["Carbohydrate (g)"] - per_meal_carbs) / per_meal_carbs
    df["fat_diff"] = abs(df["Fat (g)"] - per_meal_fat) / per_meal_fat

    df["score"] = (
        df["cal_diff"] * 0.35 +
        df["prot_diff"] * 0.25 +
        df["carb_diff"] * 0.25 +
        df["fat_diff"] * 0.15
    )

    # -------------------------------------------------
    # F) DIVERSITY SELECTION (KEY FIX)
    # -------------------------------------------------
    # Keep best 80 foods
    candidate_pool = df.sort_values("score").head(80)

    # Randomly sample from good foods
    if len(candidate_pool) > max_items:
        candidate_pool = candidate_pool.sample(
            n=max_items,
            random_state=None
        )

    # -------------------------------------------------
    # Final output
    # -------------------------------------------------
    keep_cols = [
        "Food",
        "Quantity",
        "Calories (kcal)",
        "Carbohydrate (g)",
        "Protein (g)",
        "Fat (g)",
        "score",
    ]
    keep_cols = [c for c in keep_cols if c in candidate_pool.columns]

    return candidate_pool[keep_cols].to_dict(orient="records")