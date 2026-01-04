from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from app.services.firestore_chat_store import get_messages  # must support uid+session_id


def export_session_emotions_to_txt(
    uid: str,
    session_id: str,
    out_dir: str = "chat_logs",
) -> str:
    """
    Creates a text file that contains all emotion-tagged messages
    for a given user + session_id.
    Returns the saved file path.
    """
    messages = get_messages(uid=uid, session_id=session_id)

    rows: list[dict[str, Any]] = []
    for m in messages:
        if not m.get("emotion"):
            continue

        rows.append(
            {
                "createdAtIso": m.get("createdAtIso"),
                "displayTime": m.get("displayTime"),
                "sender": m.get("sender"),
                "emotion": m.get("emotion"),
                "intent": m.get("intent"),
                "text": m.get("text"),
            }
        )

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    file_path = Path(out_dir) / f"session_{session_id}_emotions_{ts}.txt"

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"UID: {uid}\n")
        f.write(f"Session: {session_id}\n")
        f.write(f"Generated: {datetime.now(timezone.utc).isoformat()}\n")
        f.write("=" * 60 + "\n\n")

        if not rows:
            f.write("No emotion-tagged messages found.\n")
        else:
            for r in rows:
                t = r.get("createdAtIso") or r.get("displayTime")
                f.write(f"[{t}] ({r.get('sender')})\n")
                f.write(f"Emotion: {r.get('emotion')}\n")
                if r.get("intent"):
                    f.write(f"Intent: {r.get('intent')}\n")
                f.write(f"Text: {r.get('text')}\n")
                f.write("-" * 60 + "\n")

    return str(file_path)
