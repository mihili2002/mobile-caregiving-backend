def classify_text(text: str) -> str:
    """
    Classifies text into categories: medication, meal, call, appointment, activity, general.
    """
    text = text.lower()
    
    # Medication
    if any(x in text for x in ["pill", "medication", "medicine", "aspirin", "panadol", "antibiotic", "tablet", "capsule", "vitamin", "dose", "drug", "prescription"]):
        return "medication"
        
    # Meal
    if any(x in text for x in ["eat", "ate", "food", "lunch", "dinner", "breakfast", "start", "meal", "drink", "drank"]):
        return "meal"
        
    # Call / Social
    if any(x in text for x in ["call", "phone", "talk", "spoke", "visit", "met", "daughter", "son", "friend", "family"]):
        return "call"
        
    # Appointment / Health
    if any(x in text for x in ["doctor", "hospital", "clinic", "identist", "appointment", "checkup", "therapy", "nurse"]):
        return "appointment"
        
    # Activity
    if any(x in text for x in ["walk", "exercise", "read", "watch", "tv", "sleep", "nap", "woke", "shower", "bath", "garden"]):
        return "activity"
        
    return "general"
