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
        # Resolve Project Root (2 levels up from app/services/__init__.py)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        
        base_path = os.path.join(project_root, 'ml', 'models')
        
        paths = {
            'completion': os.path.join(base_path, 'completion_model.joblib'),
            'delay': os.path.join(base_path, 'delay_model.joblib'),
            'retries': os.path.join(base_path, 'retries_model.joblib'),
            'snooze': os.path.join(base_path, 'snooze_model.joblib'),
            'escalation': os.path.join(base_path, 'escalation_model.joblib')
        }
        
        if not os.path.exists(base_path):
            print(f"Warning: Model directory not found: {base_path}. Skipping model loading.")
            return

        model_completion = joblib.load(paths['completion']) if os.path.exists(paths['completion']) else None
        model_delay      = joblib.load(paths['delay']) if os.path.exists(paths['delay']) else None
        model_retries    = joblib.load(paths['retries']) if os.path.exists(paths['retries']) else None
        model_snooze     = joblib.load(paths['snooze']) if os.path.exists(paths['snooze']) else None
        model_escalation = joblib.load(paths['escalation']) if os.path.exists(paths['escalation']) else None
        
        print("AI Models verified/loaded.")
    except Exception as e:
        print(f"Error loading models: {e}")
        print("Make sure your .joblib files are in the 'ml/models/' folder.")

# Ensure we have the encoder too if needed globally, mainly used in extractor.py
