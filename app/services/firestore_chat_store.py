from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from firebase_admin import firestore
from app.core.firebase import get_db


def save_message(
    session_id: str,
    sender: str,
    text: str,
    emotion: str | None = None,
    intent: str | None = None,
):
    db = get_db()

    session_ref = db.collection("chat_sessions").document(session_id)
    session_ref.set(
        {
            "updatedAt": firestore.SERVER_TIMESTAMP,
            "createdAt": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )

    ts = datetime.now(timezone.utc)
    base_id = f"{int(ts.timestamp() * 1000)}_{sender}"

    msg_ref = session_ref.collection("messages").document(base_id)
    if msg_ref.get().exists:
        base_id = f"{base_id}_{ts.microsecond}"

    payload: dict[str, Any] = {
        "sender": sender,  # "user" or "bot"
        "text": text,
        "createdAt": firestore.SERVER_TIMESTAMP,
        "preview": (text[:60] + "...") if len(text) > 60 else text,
        "displayTime": ts.strftime("%Y-%m-%d %H:%M:%S UTC"),
    }

    if emotion is not None:
        payload["emotion"] = emotion
    if intent is not None:
        payload["intent"] = intent

    session_ref.collection("messages").document(base_id).set(payload)


def get_messages(session_id: str):
    db = get_db()

    session_ref = db.collection("chat_sessions").document(session_id)

    docs = (
        session_ref.collection("messages")
        .order_by("createdAt")
        .stream()
    )

    out = []
    for d in docs:
        data = d.to_dict() or {}
        data["id"] = d.id
        out.append(data)
    return out


def list_sessions(limit: int = 50):
    db = get_db()

    docs = (
        db.collection("chat_sessions")
        .order_by("updatedAt", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .stream()
    )

    out = []
    for d in docs:
        data = d.to_dict() or {}
        out.append(
            {
                "session_id": d.id,
                "createdAt": _to_iso(data.get("createdAt")),
                "updatedAt": _to_iso(data.get("updatedAt")),
            }
        )
    return out


def list_emotions_across_sessions(days: int = 7, limit: int = 500):
    """
    Returns bot emotions across all sessions for last N days.
    Avoids composite index by querying only on createdAt and filtering in code.
    """
    db = get_db()

    cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days > 0 else None

    q = db.collection_group("messages")
    if cutoff is not None:
        q = q.where("createdAt", ">=", cutoff)

    q = q.order_by("createdAt", direction=firestore.Query.DESCENDING).limit(limit)

    out = []
    for doc in q.stream():
        data = doc.to_dict() or {}

        if (data.get("sender") or "").lower() != "bot":
            continue
        if not data.get("emotion"):
            continue

        created = data.get("createdAt")
        created_iso = None
        if created is not None and hasattr(created, "datetime"):
            created_iso = created.datetime.replace(tzinfo=timezone.utc).isoformat()

        out.append({
            "id": doc.id,
            "emotion": data.get("emotion"),
            "intent": data.get("intent"),
            "text": data.get("text"),
            "createdAtIso": created_iso,
            "displayTime": data.get("displayTime"),
        })

    out.reverse()
    return out


def _to_iso(ts):
    if ts is None:
        return None
    try:
        dt = ts.datetime
    except Exception:
        dt = ts
    if isinstance(dt, datetime):
        return dt.astimezone(timezone.utc).isoformat()
    return str(ts)
