import os
import json
from datetime import datetime

DEBUG_MODE = os.environ.get("AI_DEBUG_MODE", "True").lower() == "true"

def log_debug(event: str, data: dict):
    """
    Logs structured debug info if enabled.
    """
    if not DEBUG_MODE:
        return

    entry = {
        "timestamp": datetime.now().isoformat(),
        "event": event,
        "data": data
    }
    
    # In a real app, this might go to Cloud Logging or a file.
    # For now, print pretty JSON to console for development.
    print(f"\n[AI DEBUG] {event}:")
    print(json.dumps(data, indent=2, default=str))
