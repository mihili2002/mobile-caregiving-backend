import joblib
import os
import pandas as pd
from sklearn.dummy import DummyClassifier, DummyRegressor

# Create models directory if it doesn't exist
if not os.path.exists('models'):
    os.makedirs('models')

print("Creating dummy models...")

# X_dummy for fitting (requires same shape as expected input)
X_dummy = pd.DataFrame([{
    'hour': 12,
    'minute': 0,
    'day_of_week': 0,
    'task_type': 1
}])
y_dummy = [1] # Single sample target matching the constant prediction

# 1. Completion Probability (Classifier returning 0.0-1.0)
model_completion = DummyClassifier(strategy="constant", constant=1) # Always predict class 1
model_completion.fit(X_dummy, y_dummy)

# 2. Expected Delay (Regressor)
model_delay = DummyRegressor(strategy="constant", constant=5.0) # 5 mins delay
model_delay.fit(X_dummy, [5.0])

# 3. Expected Retries (Regressor)
model_retries = DummyRegressor(strategy="constant", constant=0.0)
model_retries.fit(X_dummy, [0.0])

# 4. Expected Snooze (Regressor)
model_snooze = DummyRegressor(strategy="constant", constant=0.0)
model_snooze.fit(X_dummy, [0.0])

# 5. Escalation Required (Classifier 0 or 1)
model_escalation = DummyClassifier(strategy="constant", constant=0)
model_escalation.fit(X_dummy, [0])

# Save them
try:
    joblib.dump(model_completion, 'models/completion_model.joblib')
    joblib.dump(model_delay, 'models/delay_model.joblib')
    joblib.dump(model_retries, 'models/retries_model.joblib')
    joblib.dump(model_snooze, 'models/snooze_model.joblib')
    joblib.dump(model_escalation, 'models/escalation_model.joblib')
    print("✅ Dummy models created in 'models/' folder.")
except Exception as e:
    print(f"Error saving models: {e}")
