import re
from datetime import datetime

def parse_task_intent(text: str) -> dict:
    """
    Refined rule-based logic to extract task name, time, and offset.
    """
    text = text.lower().strip()
    
    # 1. Detection of Termination
    termination_keywords = [
        "nothing more", "no more", "that is all", "that's all", "thats all", 
        "all done", "nothing else", "no thanks", "no, thank you", "goodbye", 
        "exit", "finished", "all set", "everything", "stop", "cancel", "no"
    ]
    if any(k in text for k in termination_keywords) or text == "no":
        return {"is_task_request": False, "is_termination": True}

    # 2. Check for Conversational Cues
    cues_positive = ["yes", "yeah", "sure", "ok", "okay", "add more", "correct", "yep"]
    cues_negative = ["no", "nope", "not now", "nothing"] # "nothing more" handled above
    
    is_positive = any(re.search(rf"\b{k}\b", text) for k in cues_positive)
    is_negative = any(re.search(rf"\b{k}\b", text) for k in cues_negative)

    # 3. Check for Task Creation intent
    creation_keywords = ["add", "remind", "schedule", "appointment", "call", "meeting", "create", "set", "remember"]
    is_task_request = any(k in text for k in creation_keywords)
    
    if is_positive and not is_task_request:
        return {"is_task_request": False, "is_continuation": True}
    
    if not is_task_request:
        return {"is_task_request": False}

    # 3. Extract Date Offset
    date_offset = 0
    if "tomorrow" in text:
        date_offset = 1
    elif "next week" in text:
        date_offset = 7
    
    # 4. Extract Time 
    # First try standard format (HH:MM AM/PM or HH.MM AM/PM) with support for dots in a.m./p.m.
    time_str = None
    # Regex explains:
    # (\d{1,2})       : Hour (1-12 or 0-23)
    # [:.]            : Separator (colon or dot)
    # (\d{2})         : Minute
    # \s*             : Optional space
    # (a\.?m\.?|p\.?m\.?)? : Optional AM/PM with optional dots (case insensitive via flag or logic)
    time_match = re.search(r'(\d{1,2})[:.](\d{2})\s*(a\.?m\.?|p\.?m\.?)?', text)
    
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        meridiem = time_match.group(3)
        
        if meridiem:
            meridiem = meridiem.replace(".", "").lower() # normalize p.m. -> pm
            if meridiem == "pm" and hour < 12:
                hour += 12
            elif meridiem == "am" and hour == 12:
                hour = 0
        
        time_str = f"{hour:02d}:{minute:02d}"
    else:
        # Try to match 3-4 digit time like "245" or "1430"
        compact_time = re.search(r'\b(\d{3,4})\b', text)
        if compact_time:
            digits = compact_time.group(1)
            if len(digits) == 3:  # e.g., "245" = 2:45
                hour = int(digits[0])
                minute = int(digits[1:])
            else:  # e.g., "1430" = 14:30
                hour = int(digits[:2])
                minute = int(digits[2:])
            
            # Validate time
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                time_str = f"{hour:02d}:{minute:02d}"
        else:
            # Keyword-based times
            if "morning" in text: time_str = "08:00"
            elif "afternoon" in text: time_str = "14:00"
            elif "evening" in text: time_str = "18:00"
            elif "night" in text: time_str = "20:00"
            elif "noon" in text: time_str = "12:00"

    # 5. Extract Task Name (Heuristic: extract what's between "me to"/"reminder for"/"add" and "at"/"tomorrow"/...)
    # Start markers
    start_markers = ["add", "remind me to", "remind me for", "reminder for", "schedule", "create", "set", "remember to"]
    # End markers
    end_markers = ["at", "on", "tomorrow", "today", "next week", "this evening", "in the morning"]

    clean_text = text
    # Heuristic: Start after the first creation verb
    start_inx = 0
    for marker in start_markers:
        if marker in clean_text:
            start_inx = clean_text.find(marker) + len(marker)
            break
    
    # Heuristic: End before the first time/date marker (Using regex boundaries to avoid partial matches like 'at' in 'water')
    end_inx = len(clean_text)
    # Slice only the relevant part to search
    search_area = clean_text[start_inx:]
    
    first_end_marker_pos = len(search_area)
    
    for marker in end_markers:
        # mimic \bMARKER\b but marker might contain spaces 'in the morning'
        # simpler: check if marker exists in search_area
        # To match "at" but not "water", we can check boundaries.
        # But some markers have spaces.
        # Robust way: re.search(r'\b' + re.escape(marker) + r'\b', search_area)
        
        m_match = re.search(r'\b' + re.escape(marker) + r'\b', search_area)
        if m_match:
            pos = m_match.start()
            if pos < first_end_marker_pos:
                first_end_marker_pos = pos
                
    end_inx = start_inx + first_end_marker_pos
            
    task_name = clean_text[start_inx:end_inx].strip()
    
    # Fallback if too short or empty
    if not task_name or len(task_name) < 2:
        # Just clean up the original text as a fallback
        task_name = re.sub(r'\b(add|remind|schedule|tomorrow|today|at|on|for|me|to)\b', '', text).strip()
    
    # Final cleanup
    task_name = re.sub(r'\s+', ' ', task_name).strip()
    task_name = task_name.capitalize() if task_name else "New Task"

    return {
        "is_task_request": True,
        "task_name": task_name,
        "time": time_str or "12:00",
        "date_offset": date_offset
    }
