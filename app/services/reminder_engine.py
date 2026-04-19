# app/services/reminder_engine.py

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from firebase_admin import firestore

from app.services.logger import log_debug
from app.services.task_state_service import (
    mark_reminder_triggered,
    mark_missed,
    mark_escalated,
    transition_task_status,
)
from app.services.notification_service import send_voice_reminder_notification


ACTIVE_STATUSES = {
    "scheduled",
    "upcoming",
    "reminder_triggered",
    "acknowledged",
    "snoozed",
    "in_progress",
}


def parse_iso(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str)
    except Exception:
        return None


def now_utc() -> datetime:
    return datetime.utcnow()


def is_task_active(task: Dict[str, Any]) -> bool:
    return task.get("status") in ACTIVE_STATUSES


def has_task_expired(task: Dict[str, Any], now: datetime) -> bool:
    valid_until = parse_iso(task.get("validUntil"))
    if not valid_until:
        return False
    if task.get("completed") is True:
        return False
    return now > valid_until


def should_mark_upcoming(task: Dict[str, Any], now: datetime, lead_minutes: int = 10) -> bool:
    if task.get("status") != "scheduled":
        return False

    scheduled_at = parse_iso(task.get("scheduledAt"))
    if not scheduled_at:
        return False

    return scheduled_at - timedelta(minutes=lead_minutes) <= now < scheduled_at


def should_trigger_initial_reminder(task: Dict[str, Any], now: datetime) -> bool:
    if task.get("status") not in {"scheduled", "upcoming"}:
        return False

    scheduled_at = parse_iso(task.get("scheduledAt"))
    if not scheduled_at:
        return False

    last_reminder = parse_iso(task.get("lastReminderAt"))
    if last_reminder is not None:
        return False

    return now >= scheduled_at


def should_trigger_snoozed_reminder(task: Dict[str, Any], now: datetime) -> bool:
    if task.get("status") != "snoozed":
        return False

    snoozed_until = parse_iso(task.get("snoozedUntil"))
    if not snoozed_until:
        return False

    return now >= snoozed_until


def should_trigger_retry(task: Dict[str, Any], now: datetime) -> bool:
    """
    Retry only if:
    - task already reminded
    - task not completed
    - retry count below max
    - enough time passed since last reminder
    - task still within valid window
    """
    if task.get("status") not in {"reminder_triggered", "acknowledged", "in_progress"}:
        return False

    if task.get("completed") is True:
        return False

    retry_count = int(task.get("retryCount", 0) or 0)
    max_retries = int(task.get("maxRetries", 0) or 0)
    if retry_count >= max_retries:
        return False

    last_reminder = parse_iso(task.get("lastReminderAt"))
    if not last_reminder:
        return False

    retry_interval = int(task.get("retryIntervalMinutes", 10) or 10)
    next_retry_time = last_reminder + timedelta(minutes=retry_interval)

    valid_until = parse_iso(task.get("validUntil"))
    if valid_until and next_retry_time > valid_until:
        return False

    return now >= next_retry_time


def build_reminder_text(task: Dict[str, Any]) -> str:
    task_name = task.get("task_name", "your task")
    task_type = task.get("type", "common")

    if task_type == "medication":
        return f"It is time to take {task_name}."
    if task_type == "therapist":
        return f"It is time for {task_name}."
    return f"It is time for {task_name}."


def get_user_fcm_token(db, uid: str) -> Optional[str]:
    try:
        doc = db.collection("elder_profiles").document(uid).get()
        if not doc.exists:
            return None
        return doc.to_dict().get("fcm_token")
    except Exception as e:
        log_debug("fcm_lookup_error", {"uid": uid, "error": str(e)})
        return None


def trigger_voice_reminder(
    db,
    uid: str,
    schedule_doc_ref,
    task: Dict[str, Any],
    category: str = "routine",
) -> bool:
    """
    Marks the task as reminder_triggered, increments retry count when relevant,
    and sends a push notification to the mobile app.
    """
    task_id = task.get("id")
    task_name = task.get("task_name", "Task")
    if not task_id:
        return False

    current_retry_count = int(task.get("retryCount", 0) or 0)
    last_reminder_exists = task.get("lastReminderAt") is not None

    extra_patch = {
        "lastReminderAt": now_utc().isoformat(),
    }

    # Increment retry count only for subsequent reminders, not first reminder
    if last_reminder_exists:
        extra_patch["retryCount"] = current_retry_count + 1

    transition_task_status(
        db=db,
        schedule_doc_ref=schedule_doc_ref,
        uid=uid,
        task_id=task_id,
        new_status="reminder_triggered",
        actor="system",
        extra_patch=extra_patch,
        event_type="reminder_sent",
        meta={
            "task_name": task_name,
            "category": category,
            "retryCount": extra_patch.get("retryCount", current_retry_count),
        },
        confidence="high",
    )

    token = get_user_fcm_token(db, uid)
    if not token:
        log_debug("missing_fcm_token", {"uid": uid, "task": task_name})
        return False

    reminder_text = build_reminder_text(task)

    # Placeholder audio url. Replace later if you generate TTS audio files.
    audio_url = "local://voice-reminder"

    sent = send_voice_reminder_notification(
        token=token,
        message_text=reminder_text,
        audio_url=audio_url,
        category=category,
    )

    log_debug("reminder_triggered", {
        "uid": uid,
        "task_id": task_id,
        "task_name": task_name,
        "sent": sent,
    })
    return sent


def process_task(
    db,
    uid: str,
    schedule_doc_ref,
    task: Dict[str, Any],
    now: datetime,
):
    task_id = task.get("id")
    if not task_id:
        return

    if not is_task_active(task):
        return

    # 1. If expired and not completed => missed
    if has_task_expired(task, now):
        try:
            mark_missed(db, schedule_doc_ref, uid, task_id)
            log_debug("task_marked_missed", {"uid": uid, "task_id": task_id})

            if task.get("escalateOnMiss") is True:
                mark_escalated(db, schedule_doc_ref, uid, task_id)
                log_debug("task_escalated", {"uid": uid, "task_id": task_id})
        except Exception as e:
            log_debug("task_expiry_error", {"uid": uid, "task_id": task_id, "error": str(e)})
        return

    # 2. Move scheduled task to upcoming
    if should_mark_upcoming(task, now):
        try:
            transition_task_status(
                db=db,
                schedule_doc_ref=schedule_doc_ref,
                uid=uid,
                task_id=task_id,
                new_status="upcoming",
                actor="system",
                extra_patch={},
                event_type="upcoming",
                meta={"task_name": task.get("task_name", "Task")},
                confidence="high",
            )
            log_debug("task_marked_upcoming", {"uid": uid, "task_id": task_id})
        except Exception as e:
            log_debug("upcoming_error", {"uid": uid, "task_id": task_id, "error": str(e)})
        return

    # 3. First reminder at scheduled time
    if should_trigger_initial_reminder(task, now):
        trigger_voice_reminder(db, uid, schedule_doc_ref, task)
        return

    # 4. Reminder after snooze period
    if should_trigger_snoozed_reminder(task, now):
        trigger_voice_reminder(db, uid, schedule_doc_ref, task)
        return

    # 5. Retry reminder if still unfinished
    if should_trigger_retry(task, now):
        trigger_voice_reminder(db, uid, schedule_doc_ref, task)
        return


def process_schedule_document(db, schedule_doc) -> Dict[str, Any]:
    """
    Processes one schedule document and returns a summary.
    """
    data = schedule_doc.to_dict() or {}
    uid = data.get("uid") or data.get("userId")
    date_str = data.get("date")
    tasks = data.get("tasks", [])

    summary = {
        "uid": uid,
        "date": date_str,
        "processed_tasks": 0,
    }

    if not uid or not tasks:
        return summary

    now = now_utc()
    schedule_doc_ref = schedule_doc.reference

    for task in tasks:
        try:
            process_task(db, uid, schedule_doc_ref, task, now)
            summary["processed_tasks"] += 1
        except Exception as e:
            log_debug("process_task_error", {
                "uid": uid,
                "date": date_str,
                "task_id": task.get("id"),
                "error": str(e),
            })

    return summary


def process_todays_schedules() -> List[Dict[str, Any]]:
    """
    Process all schedule documents for today.
    Call this from a cron job, scheduler, or manual admin endpoint.
    """
    db = firestore.client()
    today = now_utc().strftime("%Y-%m-%d")

    docs = db.collection("schedules").where("date", "==", today).stream()
    results = []

    for doc in docs:
        try:
            result = process_schedule_document(db, doc)
            results.append(result)
        except Exception as e:
            log_debug("process_schedule_error", {
                "schedule_id": doc.id,
                "error": str(e),
            })

    return results