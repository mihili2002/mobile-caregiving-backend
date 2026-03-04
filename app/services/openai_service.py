import os
import json
import requests
from typing import Dict, Any, Optional
from app.services.logger import log_debug

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_URL = "https://api.openai.com/v1/chat/completions"

# In-memory store for multi-turn conversation history
# session_id -> list of message dicts
chat_history = {}

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
3. Task Detection: If the user wants to add a task, identify the name, time, and day.

OUTPUT FORMAT:
Provide your friendly spoken response as the main text.
If you detect a task creation intent, wrap extraction details in a special tag: [TASK: {"name": "...", "time": "HH:MM", "day": "today/tomorrow"}]
IMPORTANT: When you generate a [TASK:] tag, your spoken response MUST ask for confirmation (e.g., "Would you like me to add that to your schedule?") instead of saying it's already done.
Always prioritize being a friend first.

Example:
User: "hello alex"
Alex: "Hello there! It's so good to hear from you. How are you feeling today?"

User: "good evening"
Alex: "Good evening! I'm so glad to see you. How was your afternoon? Did you manage to take your medicine at 5 PM?"
"""

RECALL_SYSTEM_PROMPT = """
You are Alex, a caring assistant helping an elderly user recall their day.
Your goal is to answer questions about past activities and task statuses using the provided context.

GUIDELINES:
1. Be precise but warm: If a task is marked "Completed", say so naturally. If it's "Pending" or "Missing", be gentle.
2. Use the "CURRENT CONTEXT" provided: This contains the user's schedule and semantic memories.
3. If the user asks a general question not found in context, answer based on your general knowledge but prioritze the user's specific history.
4. Keep it short and clear.
"""

def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

async def process_voice_with_llm(text: str, uid: str, session_id: str, context: Optional[str] = None, system_prompt: Optional[str] = None) -> Dict[str, Any]:
    """
    Sends user text to OpenAI with conversation history and returns a natural response.
    'context' can be used to provide current schedule info, medication status, etc.
    'system_prompt' can override the default coach prompt (e.g., for memory recall).
    """
    if not OPENAI_API_KEY:
        log_debug("openai_error", {"error": "API Key missing"})
        return {"reply": "I'm having trouble connecting to my brain right now. Please try again later.", "intent": "error"}

    if not text.strip():
        return {"reply": "Pardon me? I didn't quite catch that. Could you repeat it?", "intent": "unclear"}

    # Initialize or fetch history
    if session_id not in chat_history:
        prompt = system_prompt or SYSTEM_PROMPT
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
        "temperature": 0.8, # Slightly higher for more varied small talk
        "max_tokens": 300
    }

    try:
        response = requests.post(OPENAI_URL, headers=_headers(), json=payload, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        raw_reply = data['choices'][0]['message']['content'].strip()
        
        # Append assistant message to history
        chat_history[session_id].append({"role": "assistant", "content": raw_reply})
        
        # Parse for [TASK: ...] tag
        task_data = None
        clean_reply = raw_reply
        import re
        task_match = re.search(r'\[TASK:\s*(\{.*?\})\]', raw_reply, re.DOTALL)
        if task_match:
            try:
                task_json = task_match.group(1)
                task_data = json.loads(task_json)
                clean_reply = raw_reply.replace(task_match.group(0), "").strip()
            except Exception as e:
                log_debug("parsing_error", {"error": str(e), "raw": task_json})

        return {
            "reply": clean_reply,
            "task": task_data,
            "intent": "task_detected" if task_data else "chat"
        }

    except Exception as e:
        log_debug("openai_api_error", {"error": str(e)})
        return {"reply": "I'm sorry, I'm a bit confused right now. Could you say that again?", "intent": "error"}
