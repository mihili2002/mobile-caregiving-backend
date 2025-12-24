"""
Inference helper for Member1 meal planning models.

This module loads trained ML artifacts and performs
nutrition target predictions.

Models expected under:
ml/member1_meal_plan/trained/
"""

from pathlib import Path
from typing import Dict
import joblib
import pandas as pd

# -------------------------------
# Paths
# -------------------------------
BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "trained"

# -------------------------------
# Load artifacts (loaded once)
# -------------------------------
calorie_model = joblib.load(MODEL_DIR / "calorie_model.pkl")
protein_model = joblib.load(MODEL_DIR / "protein_model.pkl")
carb_model = joblib.load(MODEL_DIR / "carb_model.pkl")
fat_model = joblib.load(MODEL_DIR / "fat_model.pkl")
mealplan_model = joblib.load(MODEL_DIR / "mealplan_model.pkl")

label_encoders = joblib.load(MODEL_DIR / "label_encoders.pkl")
feature_columns = joblib.load(MODEL_DIR / "feature_columns.pkl")


# -------------------------------
# Safe categorical encoding
# -------------------------------
def safe_encode(encoder, value):
    value = str(value)
    classes = list(encoder.classes_)
    if value not in classes:
        value = "nan" if "nan" in classes else classes[0]
    return encoder.transform([value])[0]


# -------------------------------
# Public inference API
# -------------------------------
def predict_nutrition(features: Dict) -> Dict:
    """
    Perform nutrition prediction for one elder.

    features: dict of user input fields
    returns: nutrition targets
    """

    df = pd.DataFrame([features])

    # encode categoricals
    for col, encoder in label_encoders.items():
        if col in df.columns:
            df[col] = df[col].apply(lambda v: safe_encode(encoder, v))

    # enforce correct feature order
    df = df[feature_columns]

    results = {
        "Recommended_Calories": float(calorie_model.predict(df)[0]),
        "Recommended_Protein": float(protein_model.predict(df)[0]),
        "Recommended_Carbs": float(carb_model.predict(df)[0]),
        "Recommended_Fats": float(fat_model.predict(df)[0]),
    }

    encoded_plan = mealplan_model.predict(df)[0]
    results["Recommended_Meal_Plan"] = label_encoders[
        "Recommended_Meal_Plan"
    ].inverse_transform([encoded_plan])[0]

    return results
