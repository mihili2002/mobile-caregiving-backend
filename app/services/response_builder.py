from datetime import datetime

def format_timestamp(iso_str: str) -> str:
    """
    Converts ISO timestamp to elder-friendly spoken format.
    E.g. "2023-12-23T09:00:00" -> "Today at 9 AM" or "Yesterday afternoon"
    """
    try:
        dt = datetime.fromisoformat(iso_str)
        now = datetime.now()
        delta = now - dt

        time_str = dt.strftime("%I:%M %p").lstrip("0") # "9:00 AM"

        if dt.date() == now.date():
            return f"Today at {time_str}"
        elif (now.date() - dt.date()).days == 1:
            return f"Yesterday at {time_str}"
        else:
            # Fallback for older dates
            return dt.strftime("%A, %B %d, at %I:%M %p").replace(" 0", " ")
    except:
        return ""

def build_recall_response(memories: list, time_range: tuple, uncertainty_level: str = "low", ask_confirmation: bool = False) -> str:
    """
    Constructs a spoken response based on memories and uncertainty.
    uncertainty_level: 'high' (confident), 'medium' (unsure), 'low' (not found/ambiguous)
    ask_confirmation: If True, append "Is that correct?" (Used for medications)
    """
    
    if not memories:
        return "I couldn't find that in your recent memories. Would you like me to save it for you?"

    # 1. Uncertainty Prefix
    prefix = ""
    if uncertainty_level == "high":
        prefix = "I remember: "
    elif uncertainty_level == "medium":
        prefix = "I think "
    elif uncertainty_level == "ambiguous":
         return "I found two similar memories. Did you mean the one from " + format_timestamp(memories[0]['metadata'].get('timestamp', '')) + "?"
    else:
         prefix = "I found this: "

    # 2. Limit List (Max 3)
    items = memories[:3]
    remaining = len(memories) - 3

    parts = []
    for m in items:
        ts = m['metadata'].get('timestamp')
        time_phrase = format_timestamp(ts) if ts else "recently"
        
        text = m['text']
        # Ensure text acts as a clause
        if not text.endswith('.'):
             text += "."
             
        parts.append(f"{time_phrase}, you said: {text}")

    # Combine
    response = prefix + " ".join(parts)
    
    if remaining > 0:
        response += f" And {remaining} other things."

    # 3. Confirmation
    if ask_confirmation:
        response += " Is that correct?"

    return response
