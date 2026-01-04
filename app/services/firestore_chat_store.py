from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from firebase_admin import firestore


# -------------------------
# Helpers
# -------------------------
def _user_session_ref(db, uid: str, session_id: str):
    return (
        db.collection("users")
        .document(uid)
        .collection("chat_sessions")
        .document(session_id)
    )


def _to_iso(ts):
    if ts is None:
        return None
    # Firestore Timestamp has .datetime in firebase_admin
    try:
        dt = ts.datetime
    except Exception:
        dt = ts
    if isinstance(dt, datetime):
        return dt.astimezone(timezone.utc).isoformat()
    return str(ts)


# -------------------------
# Core API
# -------------------------
def save_message(
    uid: str,
    session_id: str,
    sender: str,
    text: str,
    emotion: str | None = None,
    intent: str | None = None,
):
    """
    Save a single message under:
      users/{uid}/chat_sessions/{session_id}/messages/{message_id}
    """
    db = firestore.client()

    session_ref = _user_session_ref(db, uid, session_id)
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
        "uid": uid,  # ✅ optional (useful for debugging; not required in this structure)
        "session_id": session_id,  # ✅ optional convenience
    }

    if emotion is not None:
        payload["emotion"] = emotion
    if intent is not None:
        payload["intent"] = intent

    session_ref.collection("messages").document(base_id).set(payload)


def get_messages(uid: str, session_id: str):
    """
    Get messages for one user's session.
    """
    db = firestore.client()
    session_ref = _user_session_ref(db, uid, session_id)

    docs = session_ref.collection("messages").order_by("createdAt").stream()

    out = []
    for d in docs:
        data = d.to_dict() or {}
        data["id"] = d.id
        out.append(data)
    return out


def list_sessions(uid: str, limit: int = 50):
    """
    List sessions for one user.
    """
    db = firestore.client()

    docs = (
        db.collection("users")
        .document(uid)
        .collection("chat_sessions")
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


def list_emotions_across_sessions(uid: str, days: int = 7, limit: int = 500):
    """
    Returns USER emotions across this user's sessions for last N days.
    Uses collection_group('messages') BUT filters by uid in Python.
    """
    db = firestore.client()

    cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days > 0 else None

    q = db.collection_group("messages")
    if cutoff is not None:
        q = q.where("createdAt", ">=", cutoff)

    q = q.order_by("createdAt", direction=firestore.Query.DESCENDING).limit(limit * 3)

    out = []
    for doc in q.stream():
        data = doc.to_dict() or {}

        # ✅ Keep only this user's data
        if (data.get("uid") or "") != uid:
            continue

        # ✅ Only user messages
        if (data.get("sender") or "").lower() != "user":
            continue

        if not data.get("emotion"):
            continue

        created = data.get("createdAt")
        created_iso = None
        if created is not None and hasattr(created, "datetime"):
            created_iso = created.datetime.replace(tzinfo=timezone.utc).isoformat()

        out.append(
            {
                "id": doc.id,
                "emotion": data.get("emotion"),
                "text": data.get("text"),
                "createdAtIso": created_iso,
                "displayTime": data.get("displayTime"),
                "session_id": data.get("session_id"),
            }
        )

        if len(out) >= limit:
            break

    out.reverse()
    return out


def list_emotions_without_collection_group(
    uid: str,
    days: int = 7,
    limit: int = 500,
    sessions_limit: int = 50,
):
    """
    Fetch emotions WITHOUT using collection_group (no extra Firestore index needed).
    Iterates through THIS USER's recent sessions and reads their messages subcollections.
    """
    db = firestore.client()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days > 0 else None

    sess_docs = (
        db.collection("users")
        .document(uid)
        .collection("chat_sessions")
        .order_by("updatedAt", direction=firestore.Query.DESCENDING)
        .limit(sessions_limit)
        .stream()
    )

    out = []

    for s in sess_docs:
        session_id = s.id

        q = s.reference.collection("messages")

        if cutoff is not None:
            q = q.where("createdAt", ">=", cutoff)

        q = q.order_by("createdAt")

        for d in q.stream():
            data = d.to_dict() or {}

            if (data.get("sender") or "").lower() != "user":
                continue
            if not data.get("emotion"):
                continue

            out.append(
                {
                    "session_id": session_id,
                    "id": d.id,
                    "emotion": data.get("emotion"),
                    "intent": data.get("intent"),
                    "text": data.get("text"),
                    "displayTime": data.get("displayTime"),
                    "createdAtIso": _to_iso(data.get("createdAt")),
                }
            )

            if len(out) >= limit:
                return out

    return out

def list_user_emotions_in_range_without_collection_group(
    uid: str,
    start: datetime,
    end: datetime,
    limit: int = 500,
    sessions_limit: int = 80,
):
    """
    Fetch USER emotions for THIS USER between [start, end) WITHOUT collection_group.
    Iterates sessions and queries messages subcollections.
    No extra Firestore index needed.
    """
    db = firestore.client()

    sess_docs = (
        db.collection("users")
        .document(uid)
        .collection("chat_sessions")
        .order_by("updatedAt", direction=firestore.Query.DESCENDING)
        .limit(sessions_limit)
        .stream()
    )

    out = []

    for s in sess_docs:
        session_id = s.id
        q = (
            s.reference.collection("messages")
            .where("createdAt", ">=", start)
            .where("createdAt", "<", end)
            .order_by("createdAt")
        )

        for d in q.stream():
            data = d.to_dict() or {}

            if (data.get("sender") or "").lower() != "user":
                continue
            if not data.get("emotion"):
                continue

            out.append(
                {
                    "session_id": session_id,
                    "id": d.id,
                    "emotion": data.get("emotion"),
                    "intent": data.get("intent"),
                    "text": data.get("text"),
                    "displayTime": data.get("displayTime"),
                    "createdAtIso": _to_iso(data.get("createdAt")),
                }
            )

            if len(out) >= limit:
                return out

    return out
