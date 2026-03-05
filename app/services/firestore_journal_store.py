# app/services/firestore_journal_store.py
from datetime import datetime, timezone
import time
from firebase_admin import firestore
from google.api_core.exceptions import (
    ResourceExhausted,
    DeadlineExceeded,
    RetryError,
)

# =========================================================
# Small cache to reduce repeated reads (UI rebuild spam)
# key: (uid, limit) -> (expires_at_epoch, items)
# =========================================================
_LIST_CACHE: dict[tuple[str, int], tuple[float, list[dict]]] = {}
_CACHE_TTL_SECONDS = 10

# Safety cap to avoid huge reads in dev
_MAX_LIMIT = 200


# =========================================================
# CREATE JOURNAL
# =========================================================
def create_journal_entry(
    uid: str,
    audio_url: str,
    audio_path: str,
    duration_sec: int | None = None,
    transcript: str | None = None,
    source: str | None = None,
    language: str | None = None,
    stt_confidence: float | None = None,
    emotion: str | None = None,
    emotion_confidence: float | None = None,
):
    db = firestore.client()

    doc_ref = (
        db.collection("users")
        .document(uid)
        .collection("journals")
        .document()
    )
    journal_id = doc_ref.id

    preview = transcript[:80] if transcript else "Voice Journal"

    payload = {
        "journal_id": journal_id,
        "audioUrl": audio_url,
        "audioPath": audio_path,
        "durationSec": duration_sec,
        "transcript": transcript,
        "preview": preview,
        "source": source,
        "language": language,
        "sttConfidence": stt_confidence,
        "emotion": emotion,
        "emotionConfidence": emotion_confidence,
        "createdAt": firestore.SERVER_TIMESTAMP,
        "updatedAt": firestore.SERVER_TIMESTAMP,
        "displayTime": datetime.now(timezone.utc).isoformat(),
    }

    payload = {k: v for k, v in payload.items() if v is not None}
    doc_ref.set(payload)

    # Invalidate cache for this user
    for key in list(_LIST_CACHE.keys()):
        if key[0] == uid:
            _LIST_CACHE.pop(key, None)

    return journal_id


# =========================================================
# LIST JOURNALS (WITH CACHE + QUOTA PROTECTION)
# =========================================================
def list_journals_for_user(uid: str, limit: int = 50):
    limit = min(int(limit or 50), _MAX_LIMIT)

    cache_key = (uid, limit)
    now = time.time()

    # Serve from cache if valid
    cached = _LIST_CACHE.get(cache_key)
    if cached:
        expires_at, items = cached
        if now < expires_at:
            return items

    db = firestore.client()

    try:
        q = (
            db.collection("users")
            .document(uid)
            .collection("journals")
            .order_by("createdAt", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )

        items: list[dict] = []
        for doc in q:
            data = doc.to_dict() or {}
            data["id"] = doc.id

            ts = data.get("createdAt")
            if ts is not None and hasattr(ts, "datetime"):
                data["createdAtIso"] = (
                    ts.datetime.replace(tzinfo=timezone.utc).isoformat()
                )

            items.append(data)

        # Cache result
        _LIST_CACHE[cache_key] = (now + _CACHE_TTL_SECONDS, items)

        return items

    except (ResourceExhausted, DeadlineExceeded, RetryError) as e:
        # 🔥 IMPORTANT:
        # Stop 300-second retry loops and bubble up a clean signal.
        raise RuntimeError("FIRESTORE_QUOTA_EXCEEDED") from e


# =========================================================
# GET SINGLE JOURNAL
# =========================================================
def get_journal(uid: str, journal_id: str):
    db = firestore.client()

    doc = (
        db.collection("users")
        .document(uid)
        .collection("journals")
        .document(journal_id)
        .get()
    )

    if not doc.exists:
        return None

    data = doc.to_dict() or {}
    data["id"] = doc.id

    ts = data.get("createdAt")
    if ts is not None and hasattr(ts, "datetime"):
        data["createdAtIso"] = (
            ts.datetime.replace(tzinfo=timezone.utc).isoformat()
        )

    return data


# =========================================================
# DELETE JOURNAL
# =========================================================
def delete_journal(uid: str, journal_id: str) -> bool:
    db = firestore.client()

    ref = (
        db.collection("users")
        .document(uid)
        .collection("journals")
        .document(journal_id)
    )

    doc = ref.get()
    if not doc.exists:
        return False

    ref.delete()

    # Invalidate cache
    for key in list(_LIST_CACHE.keys()):
        if key[0] == uid:
            _LIST_CACHE.pop(key, None)

    return True