# app/services/task_state_service.py

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import uuid

TASK_RULES = {
    "medication": {
        "grace_minutes": 20,
        "max_retries": 2,
        "retry_interval_minutes": 5,
        "priority": "high",
        "escalate_on_miss": True,
    },
    "therapist": {
        "grace_minutes": 90,
        "max_retries": 2,
        "retry_interval_minutes": 20,
        "priority": "medium",
        "escalate_on_miss": False,
    },
    "common": {
        "grace_minutes": 30,
        "max_retries": 1,
        "retry_interval_minutes": 15,
        "priority": "medium",
        "escalate_on_miss": False,
    },
}

ALLOWED_STATUSES = {
    "scheduled",
    "upcoming",
    "reminder_triggered",
    "acknowledged",
    "snoozed",
    "in_progress",
    "completed_confirmed",
    "completed_likely",
    "skipped",
    "missed_likely",
    "missed_confirmed",
    "needs_caregiver_review",
    "escalated",
}


def utc_now() -> datetime:
    return datetime.utcnow()


def utc_now_iso() -> str:
    return utc_now().isoformat()


def combine_date_time(date_str: str, time_str: str) -> datetime:
    return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")


def get_task_rule(task_type: str) -> Dict[str, Any]:
    return TASK_RULES.get(task_type, TASK_RULES["common"])


def build_task_occurrence(
    uid: str,
    task_name: str,
    task_type: str,
    date_str: str,
    time_str: str,
    risk_level: str = "medium",
    recurrence_rule: Optional[str] = None,
) -> Dict[str, Any]:
    rule = get_task_rule(task_type)
    scheduled_dt = combine_date_time(date_str, time_str)
    valid_from = scheduled_dt.isoformat()
    valid_until = (scheduled_dt + timedelta(minutes=rule["grace_minutes"])).isoformat()

    return {
        "id": str(uuid.uuid4()),
        "uid": uid,
        "task_name": task_name,
        "time": time_str,
        "type": task_type,
        "status": "scheduled",
        "completed": False,
        "completedAt": None,
        "completedBy": None,
        "scheduledAt": scheduled_dt.isoformat(),
        "validFrom": valid_from,
        "validUntil": valid_until,
        "graceMinutes": rule["grace_minutes"],
        "retryCount": 0,
        "maxRetries": rule["max_retries"],
        "retryIntervalMinutes": rule["retry_interval_minutes"],
        "lastReminderAt": None,
        "acknowledgedAt": None,
        "startedAt": None,
        "skippedAt": None,
        "skipReason": None,
        "snoozedUntil": None,
        "priority": rule["priority"],
        "riskLevel": risk_level,
        "recurrenceRule": recurrence_rule,
        "caregiverNotified": False,
        "escalateOnMiss": rule["escalate_on_miss"],
        "createdAt": utc_now_iso(),
        "updatedAt": utc_now_iso(),
    }


def log_task_event(
    db,
    uid: str,
    task_id: str,
    event_type: str,
    actor: str,
    meta: Optional[Dict[str, Any]] = None,
    confidence: str = "medium",
):
    db.collection("task_events").add({
        "uid": uid,
        "task_id": task_id,
        "at": utc_now_iso(),
        "type": event_type,
        "actor": actor,
        "confidence": confidence,
        "meta": meta or {},
    })


def update_task_in_schedule(
    schedule_doc_ref,
    task_id: str,
    patch: Dict[str, Any],
):
    snap = schedule_doc_ref.get()
    if not snap.exists:
        raise ValueError("Schedule document not found")

    data = snap.to_dict() or {}
    tasks = data.get("tasks", [])
    updated = False

    for t in tasks:
        if t.get("id") == task_id:
            t.update(patch)
            t["updatedAt"] = utc_now_iso()
            updated = True
            break

    if not updated:
        raise ValueError("Task not found in schedule")

    schedule_doc_ref.update({"tasks": tasks})
    return tasks


def transition_task_status(
    db,
    schedule_doc_ref,
    uid: str,
    task_id: str,
    new_status: str,
    actor: str,
    extra_patch: Optional[Dict[str, Any]] = None,
    event_type: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
    confidence: str = "medium",
):
    if new_status not in ALLOWED_STATUSES:
        raise ValueError(f"Invalid status: {new_status}")

    patch = {"status": new_status}
    if extra_patch:
        patch.update(extra_patch)

    tasks = update_task_in_schedule(
        schedule_doc_ref=schedule_doc_ref,
        task_id=task_id,
        patch=patch,
    )

    log_task_event(
        db=db,
        uid=uid,
        task_id=task_id,
        event_type=event_type or new_status,
        actor=actor,
        meta=meta,
        confidence=confidence,
    )
    return tasks


def mark_reminder_triggered(db, schedule_doc_ref, uid: str, task_id: str):
    return transition_task_status(
        db=db,
        schedule_doc_ref=schedule_doc_ref,
        uid=uid,
        task_id=task_id,
        new_status="reminder_triggered",
        actor="system",
        extra_patch={"lastReminderAt": utc_now_iso()},
        event_type="reminder_sent",
        meta={},
        confidence="high",
    )


def mark_acknowledged(db, schedule_doc_ref, uid: str, task_id: str, actor: str = "elder"):
    return transition_task_status(
        db=db,
        schedule_doc_ref=schedule_doc_ref,
        uid=uid,
        task_id=task_id,
        new_status="acknowledged",
        actor=actor,
        extra_patch={"acknowledgedAt": utc_now_iso()},
        event_type="reminder_acknowledged",
        meta={},
        confidence="medium",
    )


def mark_in_progress(db, schedule_doc_ref, uid: str, task_id: str, actor: str = "elder"):
    return transition_task_status(
        db=db,
        schedule_doc_ref=schedule_doc_ref,
        uid=uid,
        task_id=task_id,
        new_status="in_progress",
        actor=actor,
        extra_patch={"startedAt": utc_now_iso()},
        event_type="in_progress",
        meta={},
        confidence="medium",
    )


def mark_completed(db, schedule_doc_ref, uid: str, task_id: str, actor: str = "elder"):
    return transition_task_status(
        db=db,
        schedule_doc_ref=schedule_doc_ref,
        uid=uid,
        task_id=task_id,
        new_status="completed_confirmed",
        actor=actor,
        extra_patch={
            "completed": True,
            "completedAt": utc_now_iso(),
            "completedBy": actor,
        },
        event_type="completed",
        meta={
            "completion_method": "voice_confirmed" if actor == "elder" else "caregiver_confirmed"
        },
        confidence="medium" if actor == "elder" else "high",
    )


def mark_snoozed(
    db,
    schedule_doc_ref,
    uid: str,
    task_id: str,
    snooze_minutes: int,
    actor: str = "elder",
):
    snooze_minutes = max(1, int(snooze_minutes))

    return transition_task_status(
        db=db,
        schedule_doc_ref=schedule_doc_ref,
        uid=uid,
        task_id=task_id,
        new_status="snoozed",
        actor=actor,
        extra_patch={
            "snoozedUntil": (utc_now() + timedelta(minutes=snooze_minutes)).isoformat()
        },
        event_type="snoozed",
        meta={"snooze_minutes": snooze_minutes},
        confidence="medium",
    )


def mark_skipped(
    db,
    schedule_doc_ref,
    uid: str,
    task_id: str,
    actor: str = "elder",
    reason: Optional[str] = None,
):
    return transition_task_status(
        db=db,
        schedule_doc_ref=schedule_doc_ref,
        uid=uid,
        task_id=task_id,
        new_status="skipped",
        actor=actor,
        extra_patch={
            "skippedAt": utc_now_iso(),
            "skipReason": reason,
            "completed": False,
        },
        event_type="skipped",
        meta={"reason": reason},
        confidence="medium",
    )


def mark_missed(db, schedule_doc_ref, uid: str, task_id: str):
    return transition_task_status(
        db=db,
        schedule_doc_ref=schedule_doc_ref,
        uid=uid,
        task_id=task_id,
        new_status="missed_likely",
        actor="system",
        extra_patch={"completed": False},
        event_type="missed",
        meta={"reason": "window_expired"},
        confidence="low",
    )


def mark_escalated(db, schedule_doc_ref, uid: str, task_id: str):
    return transition_task_status(
        db=db,
        schedule_doc_ref=schedule_doc_ref,
        uid=uid,
        task_id=task_id,
        new_status="escalated",
        actor="system",
        extra_patch={"caregiverNotified": True},
        event_type="escalation_sent",
        meta={},
        confidence="high",
    )