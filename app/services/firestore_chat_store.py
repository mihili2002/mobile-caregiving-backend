from datetime import datetime, timedelta, timezone
from firebase_admin import firestore
from google.cloud import firestore as gcf  # for Query constants


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

    # Ensure session doc exists / update timestamps + summary fields
    session_payload = {
        "session_id": session_id,
        "updatedAt": firestore.SERVER_TIMESTAMP,
        "createdAt": firestore.SERVER_TIMESTAMP,  # merge keeps first create
        "lastMessage": (text or ""),
        "lastSender": sender,
    }
    if emotion is not None:
        session_payload["lastEmotion"] = emotion
    if intent is not None:
        session_payload["lastIntent"] = intent

    session_ref.set(session_payload, merge=True)

    # Store message
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

        # Firestore timestamp -> ISO
        updated_iso = None
        ts = d.get("updatedAt")
        try:
            if ts is not None and hasattr(ts, "datetime"):
                updated_iso = (
                    ts.datetime.replace(tzinfo=timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z")
                )
        except Exception:
            updated_iso = None

        created_iso = None
        cts = d.get("createdAt")
        try:
            if cts is not None and hasattr(cts, "datetime"):
                created_iso = (
                    cts.datetime.replace(tzinfo=timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z")
                )
        except Exception:
            created_iso = None

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

            # only keep those that actually have emotion (usually bot messages)
            if d.get("emotion"):
                ts = d.get("createdAt")
                created_iso = None
                if ts is not None and hasattr(ts, "datetime"):
                    created_iso = ts.datetime.replace(tzinfo=timezone.utc).isoformat()

                items.append(
                    {
                        "session_id": sdoc.id,
                        "emotion": d.get("emotion"),
                        "text": d.get("text", ""),
                        "sender": d.get("sender"),
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

    # Delete subcollection messages
    for msg in session_ref.collection("messages").stream():
        msg.reference.delete()

    # Delete session document
    session_ref.delete()
    return True