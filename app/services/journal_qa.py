from __future__ import annotations
from datetime import datetime
import re
from typing import List, Dict, Tuple

def _tokenize(text: str) -> set[str]:
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return {t for t in text.split() if len(t) > 2}

def pick_relevant_journals(question: str, journals: List[Dict], k: int = 5) -> List[Dict]:
    """
    Very simple relevance scoring:
    score = overlap(question_tokens, transcript_tokens)
    """
    qtok = _tokenize(question)
    scored: List[Tuple[int, Dict]] = []

    for j in journals:
        transcript = (j or {}).get("transcript") or ""
        if not transcript.strip():
            continue
        score = len(qtok & _tokenize(transcript))
        if score > 0:
            scored.append((score, j))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [j for _, j in scored[:k]]

def build_context_snippet(journals: List[Dict]) -> str:
    """
    Format the chosen journals into a clean context block for the LLM.
    """
    blocks = []
    for j in journals:
        created = j.get("createdAtIso") or j.get("displayTime") or ""
        emotion = j.get("emotion") or ""
        preview = (j.get("transcript") or "").strip()
        if len(preview) > 800:
            preview = preview[:800] + "..."

        blocks.append(
            f"- Date: {created}\n"
            f"  Emotion: {emotion}\n"
            f"  Journal: {preview}"
        )

    return "\n\n".join(blocks).strip()
