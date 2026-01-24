"""
Inference logic ONLY.
NO joblib loading here.
"""

from typing import Dict
import pandas as pd
from app.services.ml_feature_mapper import map_patient_to_ml_features


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
# Core inference (stateless)
# -------------------------------
def predict_nutrition_core(features: Dict, models: Dict) -> Dict:
    """
    Perform nutrition prediction using injected models
    """

    df = map_patient_to_ml_features(features)

    label_encoders = models["label_encoders"]
    feature_columns = models["feature_columns"]

    # Encode categoricals
    for col, encoder in label_encoders.items():
        if col in df.columns:
            df[col] = df[col].apply(lambda v: safe_encode(encoder, v))

    # Enforce training feature order
    df = df[feature_columns]

    results = {
        "Recommended_Calories": float(models["calorie"].predict(df)[0]),
        "Recommended_Protein": float(models["protein"].predict(df)[0]),
        "Recommended_Carbs": float(models["carb"].predict(df)[0]),
        "Recommended_Fats": float(models["fat"].predict(df)[0]),
    }

    encoded_plan = models["mealplan"].predict(df)[0]
    results["Recommended_Meal_Plan"] = label_encoders[
        "Recommended_Meal_Plan"
    ].inverse_transform([encoded_plan])[0]

    return results