from typing import Dict, Any

def get_reminder_strategy(profile_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns a reminder strategy based on the elder's profile and risk factors.
    """
    # Logic to determine strategy based on age, tier, or other metrics
    age = int(profile_data.get("age", 70))
    tier = profile_data.get("prediction_tier", "Tier 2")
    
    # Default strategy (Tier 2 / Medium)
    strategy = {
        "expected_delay_min": 15,
        "auto_retries_count": 2,
        "max_snoozes_allowed": 3,
        "caregiver_escalation_enabled": True
    }
    
    if "Tier 1" in tier or age < 65:
        strategy = {
            "expected_delay_min": 5,
            "auto_retries_count": 1,
            "max_snoozes_allowed": 5,
            "caregiver_escalation_enabled": False
        }
    elif "Tier 3" in tier or age >= 80:
        strategy = {
            "expected_delay_min": 30,
            "auto_retries_count": 3,
            "max_snoozes_allowed": 2,
            "caregiver_escalation_enabled": True
        }
        
    return {
        "status": "success",
        "strategy": strategy
    }
