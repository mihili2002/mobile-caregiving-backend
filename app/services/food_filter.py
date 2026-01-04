# app/services/food_filter.py

import pandas as pd
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Any


# ✅ Correct path: app/services/food_filter.py -> app/data/food_database_final.csv
FOOD_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "food_database_final.csv"


# ---------------- Helpers ---------------- #

def clean_number(value) -> float:
    """
    Convert values like '80g', '110 kcal', '7.5g' -> float
    """
    if pd.isna(value):
        return 0.0
    value = str(value).strip().lower()
    match = re.findall(r"[\d\.]+", value)
    return float(match[0]) if match else 0.0


def parse_list(text: str) -> List[str]:
    """
    Convert "nuts, egg" -> ["nuts", "egg"]
    """
    if not text:
        return []
    text = str(text).strip()
    if text.lower() in ["none", "no", "n/a", "nil", "-"]:
        return []
    parts = re.split(r"[;,/]", text)
    return [p.strip().lower() for p in parts if p.strip()]


def contains_any(text: str, keywords: List[str]) -> bool:
    t = (text or "").lower()
    return any(k in t for k in keywords)


# ---------------- Load DB ---------------- #

@lru_cache(maxsize=1)
def load_food_db() -> pd.DataFrame:
    df = pd.read_csv(FOOD_DB_PATH)

    # Ensure numeric columns are clean
    numeric_cols = [
        "Quantity",
        "Calories (kcal)",
        "Carbohydrate (g)",
        "Protein (g)",
        "Fat (g)"
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = df[col].apply(clean_number)

    # Fill NaNs
    df = df.fillna(0)

    # Ensure Food is string
    if "Food" in df.columns:
        df["Food"] = df["Food"].astype(str)

    return df


# ---------------- Main Filtering ---------------- #

def get_food_recommendations(patient: Dict[str, Any], targets: Dict[str, float], max_items: int = 20):
    """
    patient -> dict from ML feature keys (Age, Gender, Chronic_Disease, Allergies, etc.)
    targets -> ML nutrient targets
    returns -> list[dict] food options
    """

    df = load_food_db().copy()

    # ------------------------------------------------
    # Patient conditions
    # ------------------------------------------------
    disease = str(patient.get("Chronic_Disease", "")).lower()
    dietary = str(patient.get("Dietary_Habits", "")).lower()
    meal_plan = str(targets.get("Recommended_Meal_Plan", "")).lower()

    allergies = parse_list(patient.get("Allergies", ""))
    aversions = parse_list(patient.get("Food_Aversions", ""))

    # ------------------------------------------------
    # (A) Dietary filters (vegetarian / vegan)
    # ------------------------------------------------
    if "vegetarian" in dietary and "Vegetarian" in df.columns:
        df = df[df["Vegetarian"].astype(str).str.lower() == "yes"]

    if "vegan" in dietary and "Vegan" in df.columns:
        df = df[df["Vegan"].astype(str).str.lower() == "yes"]

    # ------------------------------------------------
    # (B) Chronic disease rule filters (if dataset columns exist)
    # ------------------------------------------------
    # Diabetes-friendly
    if "diabetes" in disease and "Diabetic_Friendly" in df.columns:
        df = df[df["Diabetic_Friendly"].astype(str).str.lower() == "yes"]

    # Low-fat meal plan
    if ("low-fat" in meal_plan or "low fat" in meal_plan) and "Low_Fat" in df.columns:
        df = df[df["Low_Fat"].astype(str).str.lower() == "yes"]

    # Low-carb meal plan
    if "low carb" in meal_plan and "Low_Carb" in df.columns:
        df = df[df["Low_Carb"].astype(str).str.lower() == "yes"]

    # High-protein meal plan
    if "high protein" in meal_plan and "High_Protein" in df.columns:
        df = df[df["High_Protein"].astype(str).str.lower() == "yes"]

    # ------------------------------------------------
    # (C) Allergy filtering (STRONG + SAFE)
    # ------------------------------------------------
    nut_keywords = [
        "nut", "peanut", "almond", "cashew", "walnut", "pistachio", "hazelnut", "pistachios"
    ]

    for term in allergies:
        # remove foods that contain the allergy term in their name
        df = df[~df["Food"].str.lower().str.contains(term, na=False)]

    # If allergy includes nut allergy in any way -> remove nut foods
    if any("nut" in a for a in allergies) or any("peanut" in a for a in allergies):
        for nk in nut_keywords:
            df = df[~df["Food"].str.lower().str.contains(nk, na=False)]

    # Lactose intolerance (simple heuristic if dataset doesn't have column)
    if any("lactose" in a or "milk" in a for a in allergies):
        lactose_words = ["milk", "cheese", "butter", "cream", "yogurt", "curd", "ice cream"]
        for w in lactose_words:
            df = df[~df["Food"].str.lower().str.contains(w, na=False)]

    # ------------------------------------------------
    # (D) Food aversion filtering
    # ------------------------------------------------
    # If spicy is an aversion -> remove spicy foods by name keyword
    if any("spicy" in av for av in aversions):
        spicy_keywords = ["chili", "spicy", "miris", "hot"]
        for sk in spicy_keywords:
            df = df[~df["Food"].str.lower().str.contains(sk, na=False)]

    # ------------------------------------------------
    # (E) Macro matching using ALL 4 macros
    # ------------------------------------------------
    total_cal = float(targets.get("Recommended_Calories", 0) or 0)
    total_prot = float(targets.get("Recommended_Protein", 0) or 0)
    total_carbs = float(targets.get("Recommended_Carbs", 0) or 0)
    total_fat = float(targets.get("Recommended_Fats", 0) or 0)

    # Avoid division by zero
    if total_cal <= 0:
        total_cal = 1800.0
    if total_prot <= 0:
        total_prot = 60.0
    if total_carbs <= 0:
        total_carbs = 200.0
    if total_fat <= 0:
        total_fat = 60.0

    per_meal_cal = total_cal / 3.0
    per_meal_prot = total_prot / 3.0
    per_meal_carbs = total_carbs / 3.0
    per_meal_fat = total_fat / 3.0

    # Keep foods within reasonable macro ranges (adjustable)
    df = df[
        (df["Calories (kcal)"].between(per_meal_cal * 0.5, per_meal_cal * 1.6)) &
        (df["Protein (g)"].between(per_meal_prot * 0.3, per_meal_prot * 2.0)) &
        (df["Carbohydrate (g)"].between(per_meal_carbs * 0.2, per_meal_carbs * 2.0)) &
        (df["Fat (g)"].between(per_meal_fat * 0.2, per_meal_fat * 2.5))
    ]

    # ------------------------------------------------
    # (F) Score using all 4 macros
    # ------------------------------------------------
    df["cal_diff"] = (df["Calories (kcal)"] - per_meal_cal).abs()
    df["prot_diff"] = (df["Protein (g)"] - per_meal_prot).abs()
    df["carb_diff"] = (df["Carbohydrate (g)"] - per_meal_carbs).abs()
    df["fat_diff"] = (df["Fat (g)"] - per_meal_fat).abs()

    # Weighted score (tune weights as you like)
    df["score"] = (
        df["cal_diff"] * 0.40 +
        df["prot_diff"] * 0.25 +
        df["carb_diff"] * 0.20 +
        df["fat_diff"] * 0.15
    )

    df = df.sort_values("score").head(max_items)

    # Return only relevant columns
    keep_cols = ["Food", "Quantity", "Calories (kcal)", "Carbohydrate (g)", "Protein (g)", "Fat (g)", "score"]
    keep_cols = [c for c in keep_cols if c in df.columns]

    return df[keep_cols].to_dict(orient="records")
