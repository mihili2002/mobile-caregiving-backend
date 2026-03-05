import pandas as pd
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
import joblib


# -------------------------------------------------
# Paths
# -------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATASET_PATH = PROJECT_ROOT / "app" / "data" / "food_database_final.csv"

MODEL_DIR = PROJECT_ROOT / "ml" / "member1_meal_plan" / "trained"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


# -------------------------------------------------
# Load dataset
# -------------------------------------------------

df = pd.read_csv(DATASET_PATH)

features = ["Calories_num", "Carbs_num", "Protein_num", "Fat_num"]

X = df[features]

y_diabetes = df["Diabetes_Safe"]
y_hyper = df["Hypertension_Safe"]
y_heart = df["Heart_Safe"]


# -------------------------------------------------
# Train function
# -------------------------------------------------

def train_model(X, y, name):

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    model = RandomForestClassifier(
        n_estimators=200,
        random_state=42
    )

    model.fit(X_train, y_train)

    score = model.score(X_test, y_test)

    print(f"{name} accuracy:", round(score, 3))

    joblib.dump(model, MODEL_DIR / f"{name}_food_model.pkl")


# -------------------------------------------------
# Train models
# -------------------------------------------------

train_model(X, y_diabetes, "diabetes")
train_model(X, y_hyper, "hypertension")
train_model(X, y_heart, "heart")

print("Food suitability models saved successfully.")