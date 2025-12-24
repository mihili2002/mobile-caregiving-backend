# Member 1 — Meal Plan / Nutrition Model

Training code for the nutrition / meal-plan model. This folder is dedicated
to training and component-owned inference packaging.

Guidance for packaging and API integration:

- After training, export the model artifact (joblib) to:
	`ml/member1_meal_plan/trained/nutrition_model.joblib`
- Do NOT import training scripts from the API runtime. The backend loads
	the packaged artifact at startup via `app.services.ml_inference`.
- A small inference helper is provided at `ml/member1_meal_plan/inference.py`
	for local testing and component ownership.

If you prefer a centralized `ml/trained_models/` location, you can copy the
artifact there instead; update `app/services/ml_inference.py` if paths differ.
