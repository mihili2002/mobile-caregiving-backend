import joblib
import os

# Global Model Containers
model_completion = None
model_delay = None
model_retries = None
model_snooze = None
model_escalation = None

def load_models():
    """
    Loads all AI models from the 'models/' directory.
    Call this once on app startup.
    """
    global model_completion, model_delay, model_retries, model_snooze, model_escalation
    
    # print("Loading AI Models...")
    try:
        # Assuming app.py is run from the root, so 'models/' is available
        base_path = os.path.join('ml', 'models')
        
        model_completion = joblib.load(os.path.join(base_path, 'completion_model.joblib'))
        model_delay      = joblib.load(os.path.join(base_path, 'delay_model.joblib'))
        model_retries    = joblib.load(os.path.join(base_path, 'retries_model.joblib'))
        model_snooze     = joblib.load(os.path.join(base_path, 'snooze_model.joblib'))
        model_escalation = joblib.load(os.path.join(base_path, 'escalation_model.joblib'))
        
        # print("✅ All 5 Models Loaded Successfully!")
    except Exception as e:
        print(f"❌ Error loading models: {e}")
        print("Make sure your .joblib files are in the 'models/' folder.")

# Ensure we have the encoder too if needed globally, mainly used in extractor.py
