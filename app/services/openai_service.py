import os
import json
import requests
import re
from datetime import datetime
from typing import Dict, Any, Optional

from app.services.logger import log_debug

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_URL = "https://api.openai.com/v1/chat/completions"

# In-memory store for multi-turn conversation history
# session_id -> list of message dicts
chat_history: Dict[str, list] = {}

SYSTEM_PROMPT = """
You are Alex, a friendly, patient, and warm AI routine coach for elderly users.
Your goal is to help them manage their daily tasks, medications, reminders, and memories.

TONE AND STYLE:
1. Be a companion: Speak like a caring friend, not a robot or a help desk.
2. Be proactive: If the user greets you, acknowledge the time of day and maybe mention a task they have coming up.
3. Keep it short: Elders prefer concise, clear sentences.
4. NO MECHANICAL REPLIES: Never say "I'm listening, you can tell me..." or "I can help with...". Just respond naturally to the conversation.
5. Dynamic Greetings: For "good evening", say something like "Good evening! I hope you had a lovely day. Is there anything I can help you with before you wind down?"

CORE BEHAVIOR:
You must determine whether the user is:
1. creating a new task
2. controlling an existing task/reminder
3. making casual conversation
4. asking for recall or memory help

CONVERSATION RULES:
1. Handling Unclear Input: If the user's input is empty or gibberish, politely ask them to repeat.
2. Time Formatting: In your spoken reply, use natural 12-hour spoken English where possible.
3. Keep spoken replies warm, concise, and elder-friendly.
4. Always prioritize being a friend first.

TASK CREATION RULE:
If the user wants to add or schedule a new task, you MUST include this extraction tag at the end:
[TASK: {"name": "...", "time": "HH:MM", "day": "today/tomorrow/monday/...", "frequency": "once/daily"}]

When generating a [TASK:] tag:
- your spoken reply MUST ask for confirmation
- do NOT say the task has already been saved
- use HH:MM 24-hour format inside the tag
- if the user mentions time without a date, assume "today" relative to the USER TIME CONTEXT
- if the user says "every day", "daily", or "regularly", set frequency to "daily"; otherwise use "once"

TASK ACTION RULE:
If the user is referring to an existing reminder/task and wants to control or update it, include this extraction tag at the end:
[ACTION: {"type": "...", "task_ref": "current/latest", "snooze_minutes": 10, "reason": "..."}]

Allowed ACTION types:
- complete
- acknowledge
- snooze
- skip
- start
- cancel_reminder
- caregiver_help
- repeat

Examples:
User: "I took it"
[ACTION: {"type": "complete", "task_ref": "current"}]

User: "okay"
[ACTION: {"type": "acknowledge", "task_ref": "current"}]

User: "remind me later"
[ACTION: {"type": "snooze", "task_ref": "current", "snooze_minutes": 10}]

User: "skip today"
[ACTION: {"type": "skip", "task_ref": "current", "reason": "user_skipped_today"}]

User: "I am taking it now"
[ACTION: {"type": "start", "task_ref": "current"}]

User: "stop reminding me"
[ACTION: {"type": "cancel_reminder", "task_ref": "current"}]

IMPORTANT:
- If the user is clearly referring to a current reminder, prefer [ACTION:] over [TASK:].
- Do not output both [TASK:] and [ACTION:] unless absolutely necessary.
- If no structured extraction is needed, just reply naturally.
- The spoken response should sound natural and friendly, not technical.

EXAMPLES:
User: "hello alex"
Alex: "Hello there! It's so good to hear from you. How are you feeling today?"

User: "good evening"
Alex: "Good evening! I'm so glad to hear from you. How was your afternoon?"

User: "Remind me tomorrow at 8 to take my medicine"
Alex: "Of course. Would you like me to add taking your medicine tomorrow at 8 AM to your schedule?"
[TASK: {"name": "Take medicine", "time": "08:00", "day": "tomorrow", "frequency": "once"}]

User: "I already took it"
Alex: "Alright, that's good to hear. I'll mark it for you."
[ACTION: {"type": "complete", "task_ref": "current"}]
"""

RECALL_SYSTEM_PROMPT = """
You are Alex, a caring and detail-oriented routine coach helping an elderly user recall their past activities.
Your goal is to answer questions about what they've done, when they did it, and the status of their scheduled tasks.

GUIDELINES:
1. Be precise but warm: Use the CURRENT CONTEXT provided to give accurate answers.
2. If a task is completed, mention when it was completed if known.
3. If a task is acknowledged or in progress but not completed, explain that clearly.
4. If a task is snoozed, mention the delay if known.
5. If a task is skipped, say so gently.
6. If a task is missed or still pending, be gentle and offer help if appropriate.
7. If caregiver confirmation exists, mention it.
8. Semantic memories can be used to answer behavioral questions if they are present in the context.
9. Time Awareness: Help the user understand when something happened relative to now.
10. Tone: Always be the user's companion. Keep responses concise, usually 2-3 sentences.
11. If the information is not in the context, politely say you do not know for sure.

EXAMPLES:
- "Yes, you finished your morning walk at 8:30 AM. Well done."
- "It looks like your afternoon medicine has not been marked as taken yet."
- "Your caregiver marked that task as completed at 8:15 AM."
"""

RESCHEDULE_SYSTEM_PROMPT = """
You are Alex, a warm and patient AI companion helping an elderly user reschedule one of their tasks.
Your only job in this conversation is to agree on a NEW time for the task and confirm it before saving.

TASK CONTEXT will be injected above. It tells you: the task name and the current date/time.

FLOW YOU MUST FOLLOW:
1. If the user has not yet said a time, gently ask for it.
2. When the user mentions ANY time (spoken, approximate, partial, or relative), reflect it back in a friendly confirmation question.
   - e.g. "Great! Shall I move it to 6:30 this evening?"
   - Use natural 12-hour English in your reply (e.g. "6:30 PM" not "18:30").
   - Include the tag: [RESCHEDULE: {"date": "YYYY-MM-DD", "time": "HH:MM", "period": "AM|PM", "confirmed": false}]
3. If the user confirms (says yes, yeah, okay, sure, correct, that's right, or equivalent), reply warmly and include:
   - [RESCHEDULE: {"date": "YYYY-MM-DD", "time": "HH:MM", "period": "AM|PM", "confirmed": true}]
   - The spoken reply should be something like "Perfect! I'll remind you at 6:30 this evening. Take care!"
4. If the user says no, wrong, or wants to change the time, ask again naturally.
5. If the user says something like "around 6" or "sometime in the morning", make a reasonable assumption and confirm it:
   - e.g. "How about 6:00 PM?" with confirmed: false
6. If you cannot extract any time after 2 attempts, apologise and suggest they try again later.

TIME AND DATE RULES:
- Always set "date" to the ISO date (YYYY-MM-DD) the user intends, using the current date from TASK CONTEXT.
  - "today" → current date. "tomorrow" → current date + 1 day.
  - If no date is mentioned, default to the current date.
- Always set "period" to "AM" or "PM" — never omit it.
  - "six" in an afternoon/evening context → period: "PM", time: "06:00"
  - "six" in a morning context → period: "AM", time: "06:00"
  - "six thirty PM" → period: "PM", time: "06:30"
  - "half past six" in the evening → period: "PM", time: "06:30"
  - "6.31 PM" → period: "PM", time: "06:31"
  - "around 6" (afternoon/evening context) → period: "PM", time: "06:00"
  - "sometime this afternoon" → ask for a more specific time
  - "four o'clock" (likely PM) → period: "PM", time: "04:00"
- The "time" field is ALWAYS in 12-hour HH:MM format (01–12). Do NOT use 24-hour format.

IMPORTANT:
- NEVER save the task without getting explicit confirmation from the user.
- Do NOT ask for confirmation more than once for the same time — once confirmed, output confirmed: true.
- Keep ALL replies SHORT (1-2 sentences). Elders prefer simple, clear messages.
- Be warm, like talking to a friend — not a bot.
- Only output ONE [RESCHEDULE:] tag per message, never two.
"""


async def process_reschedule_conversation(
    text: str,
    task_name: str,
    session_id: str,
    user_now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Drives an OpenAI-powered conversation to reschedule a task.
    
    Returns:
    {
        "reply": "<natural spoken reply>",
        "time": "HH:MM" or None,          # extracted/confirmed time
        "confirmed": bool,                  # True only when user confirmed
        "intent": "task_followup" | "task_rescheduled" | "error"
    }
    """
    if not OPENAI_API_KEY:
        return {
            "reply": "I'm having a little trouble right now. Please try again.",
            "time": None,
            "confirmed": False,
            "intent": "error",
        }

    try:
        now_str = user_now.strftime("%Y-%m-%d %H:%M (%A)") if user_now else datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        task_context = (
            f"TASK CONTEXT: The user wants to reschedule their task '\"{task_name}\"'. "
            f"Current date and time: {now_str}. "
            f"Ask the user what time they would like to reschedule it to."
        )

        if session_id not in chat_history:
            full_prompt = f"{task_context}\n\n{RESCHEDULE_SYSTEM_PROMPT}"
            chat_history[session_id] = [{"role": "system", "content": full_prompt}]

        chat_history[session_id].append({"role": "user", "content": text})

        # Keep history manageable (preserve system prompt + last 8 turns)
        if len(chat_history[session_id]) > 10:
            chat_history[session_id] = [chat_history[session_id][0]] + chat_history[session_id][-9:]

        payload = {
            "model": OPENAI_MODEL,
            "messages": chat_history[session_id],
            "temperature": 0.5,
            "max_tokens": 150,
        }

        response = requests.post(OPENAI_URL, headers=_headers(), json=payload, timeout=15)
        response.raise_for_status()

        raw_reply = response.json()["choices"][0]["message"]["content"].strip()
        chat_history[session_id].append({"role": "assistant", "content": raw_reply})

        # Extract [RESCHEDULE: {...}] tag
        reschedule_data = _extract_json_tag(raw_reply, "RESCHEDULE")
        clean_reply = re.sub(r"\[RESCHEDULE:\s*\{.*?\}\]", "", raw_reply, flags=re.DOTALL).strip()

        if reschedule_data:
            extracted_time = reschedule_data.get("time")     # "HH:MM" (12-hour)
            extracted_period = reschedule_data.get("period") # "AM" | "PM"
            extracted_date = reschedule_data.get("date")     # "YYYY-MM-DD"
            confirmed = reschedule_data.get("confirmed", False)

            # Resolve unambiguous 24-hour time from the extracted 12-hour + period
            resolved_time_24 = _to_24h(extracted_time, extracted_period)

            if confirmed and resolved_time_24:
                # Clean up the session so it doesn't linger
                reset_chat_session(session_id)
                return {
                    "reply": clean_reply,
                    "date": extracted_date,
                    "time": resolved_time_24,
                    "period": extracted_period,
                    "confirmed": True,
                    "intent": "task_rescheduled",
                }
            else:
                return {
                    "reply": clean_reply,
                    "date": extracted_date,
                    "time": resolved_time_24 or extracted_time,
                    "period": extracted_period,
                    "confirmed": False,
                    "intent": "task_followup",
                }

        # No tag — LLM is still in conversation (e.g. asking for time)
        return {
            "reply": clean_reply,
            "date": None,
            "time": None,
            "period": None,
            "confirmed": False,
            "intent": "task_followup",
        }

    except requests.exceptions.RequestException as e:
        log_debug("reschedule_openai_error", {"error": str(e), "session_id": session_id})
        return {
            "reply": "I'm sorry, I'm having a bit of trouble right now. Could you try again?",
            "date": None,
            "time": None,
            "period": None,
            "confirmed": False,
            "intent": "error",
        }
    except Exception as e:
        log_debug("reschedule_error", {"error": str(e), "session_id": session_id})
        return {
            "reply": "Oops, something went wrong. Please try again.",
            "date": None,
            "time": None,
            "period": None,
            "confirmed": False,
            "intent": "error",
        }


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }


def _to_24h(time_str: Optional[str], period: Optional[str]) -> Optional[str]:
    """
    Converts a 12-hour HH:MM string and an AM/PM period into a 24-hour HH:MM string.
    Returns None if either argument is missing or unparseable.

    Examples:
        _to_24h("06:00", "PM") -> "18:00"
        _to_24h("06:30", "AM") -> "06:30"
        _to_24h("12:00", "AM") -> "00:00"  (midnight)
        _to_24h("12:00", "PM") -> "12:00"  (noon)
    """
    if not time_str or not period:
        return None
    try:
        dt = datetime.strptime(f"{time_str} {period.upper()}", "%I:%M %p")
        return dt.strftime("%H:%M")
    except ValueError:
        log_debug("to_24h_parse_error", {"time": time_str, "period": period})
        return None


def _build_system_prompt(
    base_prompt: str,
    context: Optional[str] = None,
    user_now: Optional[datetime] = None,
) -> str:
    """
    Builds the system prompt with optional user-local time context and current runtime context.
    """
    prompt = base_prompt

    if user_now:
        time_ctx = user_now.strftime("The current date and time is %Y-%m-%d %H:%M (%A).")
        prompt = f"USER TIME CONTEXT: {time_ctx}\n\n{prompt}"

    if context:
        prompt += f"\n\nCURRENT CONTEXT:\n{context}"

    return prompt


def _extract_json_tag(raw_reply: str, tag_name: str) -> Optional[Dict[str, Any]]:
    """
    Extracts a JSON payload from a tag such as:
    [TASK: {...}]
    [ACTION: {...}]
    """
    pattern = rf"\[{tag_name}:\s*(\{{.*?\}})\]"
    match = re.search(pattern, raw_reply, re.DOTALL)
    if not match:
        return None

    raw_json = match.group(1)
    try:
        return json.loads(raw_json)
    except Exception as e:
        log_debug(f"{tag_name.lower()}_parsing_error", {"error": str(e), "raw": raw_json})
        return None


def _remove_extraction_tags(raw_reply: str) -> str:
    """
    Removes structured extraction tags from the assistant text so the spoken reply remains natural.
    """
    cleaned = re.sub(r"\[TASK:\s*\{.*?\}\]", "", raw_reply, flags=re.DOTALL).strip()
    cleaned = re.sub(r"\[ACTION:\s*\{.*?\}\]", "", cleaned, flags=re.DOTALL).strip()
    return cleaned


def reset_chat_session(session_id: str) -> None:
    """
    Optional helper to clear a conversation session when needed.
    """
    if session_id in chat_history:
        del chat_history[session_id]


def get_chat_session(session_id: str) -> list:
    """
    Optional helper to inspect a session's stored history.
    """
    return chat_history.get(session_id, [])


async def process_voice_with_llm(
    text: str,
    uid: str,
    session_id: str,
    context: Optional[str] = None,
    system_prompt: Optional[str] = None,
    user_now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Sends user text to OpenAI with conversation history and returns a natural response.

    Supported behaviors preserved:
    - friendly conversation
    - task creation extraction using [TASK: {...}]
    - recall prompt switching using custom system_prompt

    New supported behavior:
    - task/reminder action extraction using [ACTION: {...}]

    Returns:
    {
        "reply": "<natural reply>",
        "task": {...} or None,
        "action_data": {...} or None,
        "intent": "task_detected" | "task_action" | "chat" | "unclear" | "error"
    }
    """
    if not OPENAI_API_KEY:
        log_debug("openai_error", {"error": "API Key missing"})
        return {
            "reply": "I'm having trouble connecting to my brain right now. Please try again later.",
            "intent": "error",
            "task": None,
            "action_data": None,
        }

    if not text or not text.strip():
        return {
            "reply": "Pardon me? I didn't quite catch that. Could you repeat it?",
            "intent": "unclear",
            "task": None,
            "action_data": None,
        }

    try:
        # Initialize session prompt only once per session
        if session_id not in chat_history:
            base_prompt = system_prompt or SYSTEM_PROMPT
            full_prompt = _build_system_prompt(
                base_prompt=base_prompt,
                context=context,
                user_now=user_now,
            )
            chat_history[session_id] = [{"role": "system", "content": full_prompt}]
        else:
            # If context is passed on later turns, append it as a lightweight system message
            # without destroying the friendly conversational continuity.
            if context:
                chat_history[session_id].append({
                    "role": "system",
                    "content": f"UPDATED CURRENT CONTEXT:\n{context}"
                })

        # Add user message
        chat_history[session_id].append({"role": "user", "content": text})

        # Keep history manageable
        # Preserve the first system prompt and the most recent messages
        if len(chat_history[session_id]) > 14:
            first_msg = chat_history[session_id][0]
            recent_msgs = chat_history[session_id][-13:]
            chat_history[session_id] = [first_msg] + recent_msgs

        payload = {
            "model": OPENAI_MODEL,
            "messages": chat_history[session_id],
            "temperature": 0.6,
            "max_tokens": 300,
        }

        response = requests.post(
            OPENAI_URL,
            headers=_headers(),
            json=payload,
            timeout=15,
        )
        response.raise_for_status()

        data = response.json()
        raw_reply = data["choices"][0]["message"]["content"].strip()

        # Save assistant raw reply in history
        chat_history[session_id].append({"role": "assistant", "content": raw_reply})

        task_data = _extract_json_tag(raw_reply, "TASK")
        action_data = _extract_json_tag(raw_reply, "ACTION")
        clean_reply = _remove_extraction_tags(raw_reply)

        intent = "chat"
        if task_data:
            intent = "task_detected"
        elif action_data:
            intent = "task_action"

        return {
            "reply": clean_reply,
            "task": task_data,
            "action_data": action_data,
            "intent": intent,
        }

    except requests.exceptions.RequestException as e:
        log_debug("openai_api_request_error", {"error": str(e), "uid": uid, "session_id": session_id})
        return {
            "reply": "I'm sorry, I'm having a little trouble responding right now. Could you try again?",
            "intent": "error",
            "task": None,
            "action_data": None,
        }
    except Exception as e:
        log_debug("openai_api_error", {"error": str(e), "uid": uid, "session_id": session_id})
        return {
            "reply": "I'm sorry, I'm a bit confused right now. Could you say that again?",
            "intent": "error",
            "task": None,
            "action_data": None,
        }