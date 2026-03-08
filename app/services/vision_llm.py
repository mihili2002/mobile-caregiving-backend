import os
import base64
import json
import re
import requests
import io
from io import BytesIO
from PIL import Image
from pdf2image import convert_from_bytes
from datetime import datetime
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
Extract all medications from the provided prescription image/PDF.
Return ONLY valid JSON with this shape:

{
  "medications": [
    {
      "drug_name": "string (clean name without 'Tab.', 'Cap.', etc.)",
      "strength": "string (normalized with space, e.g. '50 mg', '10 mg/ml')",
      "dose_pattern": "string (e.g. '1-0-1', '1 tab', '2 puffs')",
      "dose_unit": "string (e.g. 'tab', 'ml', 'cap')",
      "dose_form": "string (e.g. 'tablet', 'capsule', 'syrup', 'injection')",
      "frequency_per_day": int (numeric value, e.g. 1 if OD, 2 if BD, 3 if TDS, 4 if QID),
      "frequency_text": "string (original token like 'BD', 'OD', 'TDS', 'QID')",
      "is_prn": boolean (set true if 'SOS', 'PRN', or 'as needed' is mentioned),
      "timing": "before_meal | after_meal | with_meal | bedtime | morning | afternoon | evening | unknown",
      "duration_days": int or null,
      "duration_text": "string (e.g. '7 days', '2 weeks')",
      "from_date": "YYYY-MM-DD or null",
      "to_date": "YYYY-MM-DD or null",
      "route": "string (e.g. oral, topical)",
      "notes": "string or null",
      "confidence": float (0-1),
      "raw_text": "string (the specific line or snippet from the prescription that produced this entry)"
    }
  ]
}

Examples:
1. Input: "Tab. Allegra 120mg OD pc for 10 days"
   JSON: {"medications": [{"drug_name": "Allegra", "strength": "120 mg", "dose_pattern": "1 tab", "dose_unit": "tab", "dose_form": "tablet", "frequency_per_day": 1, "frequency_text": "OD", "is_prn": false, "timing": "after_meal", "duration_days": 10, "duration_text": "10 days", "raw_text": "Tab. Allegra 120mg OD pc for 10 days"}]}

2. Input: "Paracetamol 500mg 1 tab TDS as needed for headache"
   JSON: {"medications": [{"drug_name": "Paracetamol", "strength": "500 mg", "dose_pattern": "1 tab", "dose_unit": "tab", "dose_form": "tablet", "frequency_per_day": 3, "frequency_text": "TDS", "is_prn": true, "timing": "unknown", "notes": "for headache", "raw_text": "Paracetamol 500mg 1 tab TDS as needed for headache"}]}

Rules:
- Strip medical prefixes like 'Tab.', 'Cap.', 'Syp.', 'Inj.' from 'drug_name' and put the full word (tablet, capsule, syrup, injection) in 'dose_form'.
- Normalize 'strength' to always have a space between the number and unit (e.g., '50 mg', not '50mg').
- Separate frequency (OD/BD/numeric stats) from timing (bedtime/meals).
- Map 'ac'/'before food' to 'before_meal', 'pc'/'after food' to 'after_meal'.
- Map 'HS'/'nocte'/'at night' to 'bedtime'.
- Dates: Infer 'from_date' based on the current date provided below if not explicitly stated.
- Always include the 'raw_text' snippet for each medication.
- Return ONLY JSON. No explanations.
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
    
    # Provide system instruction via user message
    full_content = [{"type": "text", "text": prompt}] + content_parts

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "user",
                "content": full_content
            }
        ],
        "response_format": { "type": "json_object" },
        "max_tokens": 1500
    }

    r = requests.post(OPENAI_RESPONSES_URL, headers=_headers(), json=payload, timeout=60)
    if not r.ok:
        print("OPENAI STATUS:", r.status_code)
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

    today = datetime.now().strftime("%Y-%m-%d")
    extra_context = f"\nToday's date is {today}. Use this as a reference if the prescription mentions 'today' or if you need to infer a start date from a recently dated prescription."
    
    resp_json = _call_openai(content_parts, extra_instruction=extra_context)
    text = _extract_output_text(resp_json)

    try:
        data = _json_from_text(text)
        if isinstance(data, dict) and "medications" in data:
            data["raw_text"] = text # Entire LLM response text
            return data
        return {"medications": [], "raw_text": text}
    except Exception:
        repair_instruction = f"""
The previous output was not valid JSON.
Fix it and output ONLY valid JSON matching the schema.

Previous output:
{text}
"""
        resp_json2 = _call_openai(content_parts, extra_instruction=repair_instruction)
        text2 = _extract_output_text(resp_json2)
        data2 = _json_from_text(text2)
        if isinstance(data2, dict) and "medications" in data2:
            data2["raw_text"] = text2
            return data2
        return {"medications": [], "raw_text": text2}
