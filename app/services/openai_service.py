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
Your goal is to help them manage their daily tasks, medications, and memories.

TONE AND STYLE:
1. Be a companion: Speak like a caring friend, not a robot or a help desk.
2. Be proactive: If the user greets you, acknowledge the time of day and maybe mention a task they have coming up.
3. Keep it short: Elders prefer concise, clear sentences.
4. NO MECHANICAL REPLIES: Never say "I'm listening, you can tell me..." or "I can help with...". Just respond naturally to the conversation.
5. Dynamic Greetings: For "good evening", say something like "Good evening! I hope you had a lovely day. Is there anything I can help you with before you wind down?"

CONVERSATION RULES:
1. Handling Unclear Input: If the user's input is empty or gibberish, politely ask them to repeat or "Pardon me?".
2. Time Formatting: Always convert 24-hour times to natural 12-hour spoken English (e.g., '17:05' -> 'five five', '08:00' -> 'eight AM').
3. Task Detection: If the user wants to add a task, identify the name, time, and day/frequency.

OUTPUT FORMAT:
1. Provide your friendly spoken response as the main text.
2. CRITICAL: If the user wants to add a task, you MUST include the extraction tag at the end of your response:
   [TASK: {"name": "...", "time": "HH:MM", "day": "today/tomorrow", "frequency": "once/daily"}]

IMPORTANT:
- When you generate a [TASK:] tag, your spoken response MUST ask for confirmation
  (e.g., "Would you like me to add that to your schedule?") instead of saying it's already done.
- Always prioritize being a friend first.
- Date Logic: If the user mentions a time without a date (e.g., "at 8:00"), assume "today"
  relative to the USER TIME CONTEXT. Do NOT automatically jump to "tomorrow" unless explicitly asked.
- Frequency: If the user says "every day", "daily", or "regularly", set frequency to "daily". Otherwise "once".
- Time Formatting: Use HH:MM (24h) in the [TASK:] tag, but use natural 12h English in your spoken response.

EXAMPLES:
User: "hello alex"
Alex: "Hello there! It's so good to hear from you. How are you feeling today?"

User: "good evening"
Alex: "Good evening! I'm so glad to see you. How was your afternoon? Did you manage to take your medicine at 5 PM?"
"""

RECALL_SYSTEM_PROMPT = """
You are Alex, a caring and detail-oriented routine coach helping an elderly user recall their past activities.
Your goal is to answer questions about what they've done, when they did it, and the status of their scheduled tasks.

GUIDELINES:
1. Be precise but warm: Use the "CURRENT CONTEXT" provided to give accurate answers.
2. Analyzing Task Status:
   - If a task is "Completed", celebrate it briefly (e.g., "Yes, you finished your morning walk at 8:30! Well done.").
   - If it's "Pending" or "Missing", be gentle and offer help (e.g., "It looks like your afternoon medicine hasn't been marked as taken yet. Would you like me to help you with that?").
3. Semantic Memories: Use these to answer behavioral questions (e.g., "Where did I go on Tuesday?" -> "You recorded that you went to the dentist on Tuesday.").
4. Time Awareness: Help the user understand "when" things happened relative to now.
5. Tone: Always be the user's companion. Keep responses concise (2-3 sentences max).
6. If the information isn't in the context: Politely say you don't recall that specific detail but mention something related if possible.
"""


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }


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
    'context' can be used to provide current schedule info, medication status, etc.
    'system_prompt' can override the default coach prompt (e.g., for memory recall).
    """
    if not OPENAI_API_KEY:
        log_debug("openai_error", {"error": "API Key missing"})
        return {
            "reply": "I'm having trouble connecting to my brain right now. Please try again later.",
            "intent": "error",
        }

    if not text.strip():
        return {"reply": "Pardon me? I didn't quite catch that. Could you repeat it?", "intent": "unclear"}

    # Initialize or fetch history
    if session_id not in chat_history:
        prompt = system_prompt or SYSTEM_PROMPT

        # Add current time for better date reasoning
        if user_now:
            time_ctx = user_now.strftime("The current date and time is %Y-%m-%d %H:%M (%A).")
            prompt = f"USER TIME CONTEXT: {time_ctx}\n\n{prompt}"

        if context:
            prompt += f"\n\nCURRENT CONTEXT:\n{context}"

        chat_history[session_id] = [{"role": "system", "content": prompt}]

    # Append user message
    chat_history[session_id].append({"role": "user", "content": text})

    # Keep history manageable (last 11 messages including system prompt)
    if len(chat_history[session_id]) > 11:
        chat_history[session_id] = [chat_history[session_id][0]] + chat_history[session_id][-10:]

    payload = {
        "model": OPENAI_MODEL,
        "messages": chat_history[session_id],
        "temperature": 0.8,  # Slightly higher for more varied small talk
        "max_tokens": 300,
    }

    try:
        response = requests.post(OPENAI_URL, headers=_headers(), json=payload, timeout=15)
        response.raise_for_status()

        data = response.json()
        raw_reply = data["choices"][0]["message"]["content"].strip()

        # Append assistant message to history
        chat_history[session_id].append({"role": "assistant", "content": raw_reply})

        # Parse for [TASK: ...] tag
        task_data = None
        clean_reply = raw_reply

        task_match = re.search(r"\[TASK:\s*(\{.*?\})\]", raw_reply, re.DOTALL)
        if task_match:
            task_json = task_match.group(1)
            try:
                task_data = json.loads(task_json)
                clean_reply = raw_reply.replace(task_match.group(0), "").strip()
            except Exception as e:
                log_debug("parsing_error", {"error": str(e), "raw": task_json})

        return {
            "reply": clean_reply,
            "task": task_data,
            "intent": "task_detected" if task_data else "chat",
        }

    except Exception as e:
        log_debug("openai_api_error", {"error": str(e)})
        return {"reply": "I'm sorry, I'm a bit confused right now. Could you say that again?", "intent": "error"}