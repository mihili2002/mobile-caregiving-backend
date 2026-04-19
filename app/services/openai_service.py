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

def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }


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