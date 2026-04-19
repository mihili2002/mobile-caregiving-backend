from datetime import datetime, timedelta, time
import re

from typing import Optional

def extract_time_from_text(text: str) -> Optional[str]:
    """
    Extracts a time string (e.g. "14:30") from natural language text.
    Handles basic formats like "2:30 pm", "14:30", "at 4", etc.
    """
    text = text.lower()
    
    # Try 12-hour format with am/pm: "2:30 pm", "2 pm", "2pm", "2:30pm"
    match = re.search(r'\b(1[0-2]|0?[1-9])(?::([0-5][0-9]))?\s*(am|pm)\b', text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        period = match.group(3)
        
        if period == 'pm' and hour != 12:
            hour += 12
        elif period == 'am' and hour == 12:
            hour = 0
            
        return f"{hour:02d}:{minute:02d}"
        
    # Try 24-hour format: "14:30"
    match = re.search(r'\b([01]?[0-9]|2[0-3]):([0-5][0-9])\b', text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        return f"{hour:02d}:{minute:02d}"

    # Try simple number with "at": "at 4", "at 14"
    match = re.search(r'\bat\s+(1[0-2]|0?[1-9])\b', text)
    if match:
        hour = int(match.group(1))
        # This is very basic fallback assuming exact hour
        return f"{hour:02d}:00"
        
    return None

def extract_time_range(text: str):
    """
    Extracts explicit time ranges from natural language text.
    Returns (start_dt, end_dt) tuple or None if no time context found.
    All datetimes are naive but relative to 'now' (system time).
    """
    now = datetime.now()
    today_start = datetime.combine(now.date(), time.min)
    today_end = datetime.combine(now.date(), time.max)
    
    text = text.lower().strip()

    # 1. "Today"
    if "today" in text:
        return (today_start, today_end)
    
    # 2. "Yesterday"
    if "yesterday" in text:
        yesterday_start = today_start - timedelta(days=1)
        yesterday_end = today_end - timedelta(days=1)
        return (yesterday_start, yesterday_end)

    # 3. "This Morning" (05:00 - 12:00)
    if "this morning" in text:
        return (datetime.combine(now.date(), time(5, 0)), 
                datetime.combine(now.date(), time(12, 0)))

    # 4. "This Afternoon" (12:00 - 17:00)
    if "this afternoon" in text:
        return (datetime.combine(now.date(), time(12, 0)), 
                datetime.combine(now.date(), time(17, 0)))

    # 5. "This Evening" (17:00 - 22:00)
    if "this evening" in text or "tonight" in text:
        return (datetime.combine(now.date(), time(17, 0)), 
                datetime.combine(now.date(), time(22, 0)))

    # 6. "Last Week" (Previous Mon-Sun)
    if "last week" in text:
        # monday = 0, sunday = 6
        current_weekday = now.weekday()
        # Go back to last Monday
        days_since_last_mon = current_weekday + 7
        last_mon_date = now.date() - timedelta(days=days_since_last_mon)
        last_sun_date = last_mon_date + timedelta(days=6)
        
        return (datetime.combine(last_mon_date, time.min),
                datetime.combine(last_sun_date, time.max))

    # 7. "This Week" (Mon - Now)
    if "this week" in text:
        current_weekday = now.weekday()
        this_mon_date = now.date() - timedelta(days=current_weekday)
        return (datetime.combine(this_mon_date, time.min), now)
        
    # 8. "Last Month"
    if "last month" in text:
        # first day of current month
        first_current = now.replace(day=1)
        # last day of prev month = first_current - 1 day
        last_prev_end = first_current - timedelta(days=1)
        # first day of prev month
        first_prev = last_prev_end.replace(day=1)
        
        return (datetime.combine(first_prev.date(), time.min),
                datetime.combine(last_prev_end.date(), time.max))
                
    # 9. "This Month"
    if "this month" in text:
        first_current = now.replace(day=1)
        return (datetime.combine(first_current.date(), time.min), now)

    return None

def get_schedule_doc_id(uid, date_val):
    """
    Standardizes how we generate Firestore document IDs for schedules.
    Format: uid_YYYY-MM-DD
    """
    try:
        if isinstance(date_val, datetime):
            date_str = date_val.strftime("%Y-%m-%d")
        elif "." in date_val: # Convert DD.MM.YYYY to YYYY-MM-DD
            parts = date_val.split('.')
            date_str = f"{parts[2]}-{parts[1]}-{parts[0]}"
        else:
            # Assume YYYY-MM-DD or already correct
            date_str = str(date_val)
            
        return f"{uid}_{date_str}"
    except:
        return f"{uid}_{date_val}"

def is_last_time_query(text: str) -> bool:
    """
    Detects if the user is asking for the most recent occurrence.
    E.g. "When did I last...", "last time I...", "most recent"
    """
    text = text.lower()
    triggers = ["last time", "when did i last", "most recent", "latest"]
    return any(t in text for t in triggers)

def combine_date_time(date_str: str, time_str: str) -> str:
    """
    Combines a date string (YYYY-MM-DD) and a time string (HH:MM or H:MM)
    into an ISO 8601 timestamp (YYYY-MM-DDTHH:MM:00).
    """
    try:
        # Normalize time_str if it's H:MM
        if len(time_str.split(':')[0]) == 1:
            time_str = "0" + time_str
            
        # Basic validation/formatting to ensure it's HH:MM
        return f"{date_str}T{time_str}:00"
    except Exception:
        # Fallback to now if something goes wrong, though should be rare
        return datetime.now().isoformat()
