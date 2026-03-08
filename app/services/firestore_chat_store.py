from datetime import datetime, timedelta, timezone
from firebase_admin import firestore
from google.cloud import firestore as gcf  # for Query constants


def _ts_to_iso(ts):
    if ts is None:
        return None
    try:
        if hasattr(ts, "datetime"):
            return (
                ts.datetime.replace(tzinfo=timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            )
    except Exception:
        pass
    return None


def save_message_for_user(
    uid: str,
    session_id: str,
    sender: str,
    text: str,
    emotion: str | None = None,
    intent: str | None = None,
):
    db = firestore.client()

    session_ref = (
        db.collection("users")
        .document(uid)
        .collection("chat_sessions")
        .document(session_id)
    )

    # Set createdAt only when session does not already exist
    session_doc = session_ref.get()

    session_payload = {
        "session_id": session_id,
        "updatedAt": firestore.SERVER_TIMESTAMP,
        "lastMessage": (text or ""),
        "lastSender": sender,
    }

    if not session_doc.exists:
        session_payload["createdAt"] = firestore.SERVER_TIMESTAMP

    if emotion is not None:
        session_payload["lastEmotion"] = emotion
    if intent is not None:
        session_payload["lastIntent"] = intent

    session_ref.set(session_payload, merge=True)

    # Store message inside subcollection
    msg_ref = session_ref.collection("messages").document()
    payload = {
        "sender": sender,
        "text": text,
        "preview": (text[:80] if text else ""),
        "createdAt": firestore.SERVER_TIMESTAMP,
        "displayTime": datetime.now(timezone.utc).isoformat(),
    }

    if emotion is not None:
        payload["emotion"] = emotion
    if intent is not None:
        payload["intent"] = intent

    msg_ref.set(payload)


def list_sessions_for_user(uid: str, limit: int = 50):
    """
    Returns session list for the user.
    IMPORTANT: returns [] if none exist (not 404).
    """
    db = firestore.client()

    q = (
        db.collection("users")
        .document(uid)
        .collection("chat_sessions")
        .order_by("updatedAt", direction=gcf.Query.DESCENDING)
        .limit(limit)
        .stream()
    )

    items: list[dict] = []
    for doc in q:
        d = doc.to_dict() or {}

        updated_iso = _ts_to_iso(d.get("updatedAt"))
        created_iso = _ts_to_iso(d.get("createdAt"))

        items.append(
            {
                "session_id": d.get("session_id") or doc.id,
                "updatedAtIso": updated_iso,
                "createdAtIso": created_iso,
                "lastMessage": d.get("lastMessage") or "",
                "lastSender": d.get("lastSender") or "",
                "lastEmotion": d.get("lastEmotion"),
                "lastIntent": d.get("lastIntent"),
            }
        )

    return items


def list_session_messages_for_user(uid: str, session_id: str, limit: int = 500):
    """
    Returns messages for a single session in ascending time order.
    Returns None if session does not exist.
    """
    db = firestore.client()

    session_ref = (
        db.collection("users")
        .document(uid)
        .collection("chat_sessions")
        .document(session_id)
    )

    session_doc = session_ref.get()
    if not session_doc.exists:
        return None

    q = (
        session_ref.collection("messages")
        .order_by("createdAt", direction=gcf.Query.ASCENDING)
        .limit(limit)
        .stream()
    )

    items: list[dict] = []
    for doc in q:
        d = doc.to_dict() or {}

        created_iso = _ts_to_iso(d.get("createdAt")) or d.get("displayTime")

        items.append(
            {
                "message_id": doc.id,
                "sender": d.get("sender") or "",
                "text": d.get("text") or "",
                "preview": d.get("preview") or "",
                "emotion": d.get("emotion"),
                "intent": d.get("intent"),
                "createdAtIso": created_iso,
                "displayTime": d.get("displayTime"),
            }
        )

    return items


def list_emotions_for_user(uid: str, days: int = 7, limit: int = 500):
    db = firestore.client()

    since = None
    if days > 0:
        since = datetime.now(timezone.utc) - timedelta(days=days)

    sessions_q = (
        db.collection("users")
        .document(uid)
        .collection("chat_sessions")
        .order_by("updatedAt", direction=gcf.Query.DESCENDING)
        .limit(200)
        .stream()
    )

    items = []
    for sdoc in sessions_q:
        sref = sdoc.reference
        mq = sref.collection("messages")

        if since is not None:
            mq = mq.where("createdAt", ">=", since)

        mq = mq.order_by("createdAt", direction=gcf.Query.DESCENDING).limit(limit)

        for mdoc in mq.stream():
            d = mdoc.to_dict() or {}

            sender = (d.get("sender") or "").lower()

            # ✅ only elder/user messages with emotion
            if sender == "user" and d.get("emotion"):
                created_iso = _ts_to_iso(d.get("createdAt")) or d.get("displayTime")

                items.append(
                    {
                        "session_id": sdoc.id,
                        "emotion": d.get("emotion"),
                        "text": d.get("text", ""),
                        "sender": sender,
                        "createdAtIso": created_iso,
                    }
                )

            if len(items) >= limit:
                return items

    return items

def delete_session_for_user(uid: str, session_id: str) -> bool:
    db = firestore.client()

    session_ref = (
        db.collection("users")
        .document(uid)
        .collection("chat_sessions")
        .document(session_id)
    )

    doc = session_ref.get()
    if not doc.exists:
        return False

    # Delete all messages in subcollection
    for msg in session_ref.collection("messages").stream():
        msg.reference.delete()

    # Delete session document
    session_ref.delete()
    return True