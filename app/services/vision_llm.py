import os
import base64
import json
import re
import requests
import io
from io import BytesIO
from PIL import Image
from pdf2image import convert_from_bytes
from typing import Dict, Any, Optional

def _get_openai_key() -> str:
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return key

def _get_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/chat/completions"

def _image_bytes_to_data_url(img_bytes: bytes, mime="image/png") -> str:
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    return f"data:{mime};base64,{b64}"

# Strict schema we want the model to output (as JSON)
SCHEMA_INSTRUCTIONS = """
Return ONLY valid JSON with this shape:

{
  "medications": [
    {
      "drug_name": "string",
      "dosage": "string",
      "frequency": "string or null (e.g. '1-0-1', 'BD', 'Once daily')",
      "timing": "before_meal | after_meal | with_meal | unknown",
      "meals": ["breakfast","lunch","dinner"] or null,
      "duration": "string or null",
      "notes": "string or null"
    }
  ]
}

Rules:
- Extract ALL medication items you can see, including handwritten ones.
- Be highly adaptable: if layout is unconventional, use visual proximity and context to link drug names with their dosages and frequencies.
- If a detail is partially legible, provide your BEST guess instead of skipping the item.
- Look for frequency charts (e.g. 1-0-1 implies Morning-Afternoon-Night).
- If a timing instruction is found (e.g. "after food"), use "after_meal".
- If a field is completely missing, set it to "unknown" (or null where allowed).
- JSON only. No markdown. No backticks.
"""

def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {_get_openai_key()}",
        "Content-Type": "application/json",
    }

def _extract_output_text(resp_json: Dict[str, Any]) -> str:
    # Chat Completions structure: choices[0].message.content
    choices = resp_json.get("choices", [])
    if choices and isinstance(choices, list):
        return choices[0].get("message", {}).get("content", "").strip()
    return ""

def _json_from_text(text: str) -> Dict[str, Any]:
    """
    Try to parse JSON; if the model added extra text, attempt to extract the JSON object.
    """
    text = text.strip()
    
    # Remove markdown code blocks if present
    if text.startswith("```"):
        text = re.sub(r"^```json\s*|```\s*$", "", text, flags=re.MULTILINE)

    # Direct parse first
    try:
        return json.loads(text)
    except Exception:
        pass

    # Extract first {...} block
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        raise ValueError("No JSON object found in model output")
    return json.loads(m.group(0))

def _call_openai(content_parts: list, extra_instruction: Optional[str] = None) -> Dict[str, Any]:
    prompt = SCHEMA_INSTRUCTIONS if not extra_instruction else (SCHEMA_INSTRUCTIONS + "\n" + extra_instruction)
    
    # Provide system instruction via user message or system message
    # Here we append text prompt to the user content for vision
    
    full_content = [{"type": "text", "text": prompt}] + content_parts

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "user",
                "content": full_content
            }
        ],
        "max_tokens": 1000
    }

    r = requests.post(OPENAI_RESPONSES_URL, headers=_headers(), json=payload, timeout=60)
    if not r.ok:
        print("OPENAI STATUS:", r.status_code)
        print("OPENAI RESPONSE:", r.text)
        r.raise_for_status()
    return r.json()

def extract_with_openai_vision(file_bytes: bytes, filename: str, content_type: str) -> Dict[str, Any]:
    is_pdf = "pdf" in (content_type or "").lower() or filename.lower().endswith(".pdf")

    content_parts = []

    if is_pdf:
        pages = convert_from_bytes(file_bytes, first_page=1, last_page=2)  # first 1-2 pages
        for page in pages:
            buf = BytesIO()
            page.save(buf, format="PNG")
            data_url = _image_bytes_to_data_url(buf.getvalue(), "image/png")
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": data_url}
            })
    else:
        # Handle regular images
        mime = content_type or ""
        # OpenAI rejects 'application/octet-stream'. If we see that (or empty), 
        # use Pillow to detect the real image format.
        if not mime or "octet-stream" in mime:
            try:
                img = Image.open(BytesIO(file_bytes))
                fmt = img.format.lower()
                mime = f"image/{fmt}"
                # Normalization
                if mime == "image/jpg": mime = "image/jpeg"
            except Exception:
                # Fallback if not a valid image or Pillow fails
                mime = "image/jpeg"

        data_url = _image_bytes_to_data_url(file_bytes, mime)
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": data_url}
        })

    resp_json = _call_openai(content_parts)
    text = _extract_output_text(resp_json)

    try:
        return _json_from_text(text)
    except Exception:
        repair_instruction = f"""
The previous output was not valid JSON.
Fix it and output ONLY valid JSON matching the schema.

Previous output:
{text}
"""
        resp_json2 = _call_openai(content_parts, extra_instruction=repair_instruction)
        text2 = _extract_output_text(resp_json2)
        return _json_from_text(text2)
