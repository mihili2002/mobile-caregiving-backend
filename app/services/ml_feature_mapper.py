import pandas as pd
from typing import Union, Optional

# === EXACT feature columns used during training ===
EXPECTED_FEATURE_COLUMNS = [
    "Age",
    "Gender",
    "Height_cm",
    "Weight_kg",
    "BMI",
    "Chronic_Disease",
    "Blood_Pressure_Systolic",
    "Blood_Pressure_Diastolic",
    "Cholesterol_Level",
    "Blood_Sugar_Level",
    "Genetic_Risk_Factor",
    "Allergies",
    "Daily_Steps",
    "Exercise_Frequency",
    "Sleep_Hours",
    "Alcohol_Consumption",
    "Smoking_Habit",
    "Dietary_Habits",
    "Caloric_Intake",
    "Protein_Intake",
    "Carbohydrate_Intake",
    "Fat_Intake",
    "Preferred_Cuisine",
    "Food_Aversions",
]


def yes_no(val: Union[bool, str, None]) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, bool):
        return "Yes" if val else "No"
    return val


def map_patient_to_ml_features(patient: dict) -> pd.DataFrame:
    """
    Convert API / Firestore patient dict → ML feature DataFrame
    EXACTLY matching training schema.
    """

    height_m = patient["height_cm"] / 100
    bmi = round(patient["weight_kg"] / (height_m ** 2), 2)

    row = {
        "Age": patient.get("age"),
        "Gender": patient.get("gender"),
        "Height_cm": patient.get("height_cm"),
        "Weight_kg": patient.get("weight_kg"),
        "BMI": bmi,
        "Chronic_Disease": ",".join(patient.get("chronic_conditions", [])),
        "Blood_Pressure_Systolic": patient.get("blood_pressure", {}).get("systolic"),
        "Blood_Pressure_Diastolic": patient.get("blood_pressure", {}).get("diastolic"),
        "Cholesterol_Level": patient.get("cholesterol_mg_dl"),
        "Blood_Sugar_Level": patient.get("blood_sugar_mg_dl"),
        "Genetic_Risk_Factor": yes_no(patient.get("genetic_risk")),
        "Allergies": patient.get("food_allergies"),
        "Daily_Steps": patient.get("daily_steps"),
        "Exercise_Frequency": patient.get("exercise_frequency"),
        "Sleep_Hours": patient.get("sleep_hours"),
        "Alcohol_Consumption": yes_no(patient.get("alcohol")),
        "Smoking_Habit": yes_no(patient.get("smoking")),
        "Dietary_Habits": patient.get("dietary_habit"),
        "Caloric_Intake": patient.get("caloric_intake"),
        "Protein_Intake": patient.get("protein_intake"),
        "Carbohydrate_Intake": patient.get("carbohydrate_intake"),
        "Fat_Intake": patient.get("fat_intake"),
        "Preferred_Cuisine": patient.get("preferred_cuisine"),
        "Food_Aversions": patient.get("food_aversions"),
    }

    df = pd.DataFrame([row])
    return df[EXPECTED_FEATURE_COLUMNS]