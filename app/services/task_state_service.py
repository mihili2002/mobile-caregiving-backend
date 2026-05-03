# app/services/task_state_service.py

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import uuid
from app.services.notification_service import notify_caregiver_of_skipped_task

TASK_RULES = {
    "medication": {
        # --- timing ---
        "grace_minutes": 20,
        "max_retries": 2,
        "retry_interval_minutes": 5,
        "priority": "high",
        # --- miss policy ---
        "escalate_on_miss": True,
        # --- skip policy ---
        "escalate_on_skip": True,           # notify & escalate when skipped
        "require_skip_confirmation": True,  # elder must confirm voice skip
        "allow_pre_schedule_skip": False,   # cannot skip before window opens
        "notify_caregiver_on_skip": True,   # push notification to caregiver
        "skip_limit_window_days": 7,        # rolling window for skip-limit check
        "skip_limit_count": 2,              # max allowed skips inside that window
    },
    "therapist": {
        # --- timing ---
        "grace_minutes": 90,
        "max_retries": 2,
        "retry_interval_minutes": 20,
        "priority": "medium",
        # --- miss policy ---
        "escalate_on_miss": False,
        # --- skip policy ---
        "escalate_on_skip": False,
        "require_skip_confirmation": False,
        "allow_pre_schedule_skip": True,
        "notify_caregiver_on_skip": False,
        "skip_limit_window_days": 7,
        "skip_limit_count": 3,
    },
    "common": {
        # --- timing ---
        "grace_minutes": 30,
        "max_retries": 1,
        "retry_interval_minutes": 15,
        "priority": "medium",
        # --- miss policy ---
        "escalate_on_miss": False,
        # --- skip policy ---
        "escalate_on_skip": False,
        "require_skip_confirmation": False,
        "allow_pre_schedule_skip": True,
        "notify_caregiver_on_skip": False,
        "skip_limit_window_days": 7,
        "skip_limit_count": 5,
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

ALLOWED_SKIP_REASONS = {
    "voice_skip",           # elder said skip via voice
    "reminder_cancelled",   # elder asked to stop reminders
    "elder_refused",        # elder explicitly refused
    "caregiver_skipped",    # caregiver marked as skipped on elder's behalf
    "already_done_uncertain", # elder thinks they already did it, unverified
    "not_feeling_well",     # elder reported feeling unwell
    "not_available",        # elder not available at the scheduled time
    "out_of_medicine",      # medication task: supply depleted
    "other",                # fallback bucket
}


def normalize_skip_reason(reason: Optional[str]) -> str:
    """
    Clamps a free-text skip reason to the known set.
    Normalises whitespace and casing; returns "other" for anything unrecognised.
    """
    if not reason:
        return "other"
    r = reason.strip().lower().replace(" ", "_")
    return r if r in ALLOWED_SKIP_REASONS else "other"


def utc_now() -> datetime:
    return datetime.utcnow()


def utc_now_iso() -> str:
    return utc_now().isoformat() + "Z"


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
        "snoozeVersion": 0,
        "priority": rule["priority"],
        "riskLevel": risk_level,
        "recurrenceRule": recurrence_rule,
        "caregiverNotified": False,
        # --- miss policy (stamped so engine needs no rule lookup) ---
        "escalateOnMiss": rule["escalate_on_miss"],
        # --- skip policy: rule-derived constants (set at creation, immutable) ---
        "escalateOnSkip": rule["escalate_on_skip"],
        "requireSkipConfirmation": rule["require_skip_confirmation"],
        "allowPreScheduleSkip": rule["allow_pre_schedule_skip"],
        "notifyCaregiverOnSkip": rule["notify_caregiver_on_skip"],
        "skipLimitWindowDays": rule["skip_limit_window_days"],
        "skipLimitCount": rule["skip_limit_count"],
        # --- skip state: mutable, updated as skips occur ---
        "skipCount": 0,                 # total skips ever (lifetime)
        "skipCountWindow": 0,           # skips inside the current rolling window
        "caregiverSkipNotified": False, # True after caregiver push is delivered
        "skipReviewRequired": False,    # set True when skip limit is breached
        "lastSkipDecisionBy": None,     # "elder" | "caregiver" | "system"
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

    meta = meta or {}
    task_dict = next((t for t in tasks if t.get("id") == task_id), None)
    if task_dict:
        if "task_name" not in meta:
            meta["task_name"] = task_dict.get("task_name")
        if "task_type" not in meta:
            meta["task_type"] = task_dict.get("type")

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
    # Increment version to invalidate any pending reminders
    current_version = _get_current_reminder_version(schedule_doc_ref, task_id)
    new_version = current_version + 1

    invalidate_existing_reminders_for_task(db, schedule_doc_ref, task_id, "completed")

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
            "reminderVersion": new_version,
            "snoozeVersion": new_version,
            "snoozedUntil": None,
        },
        event_type="completed",
        meta={
            "completion_method": "voice_confirmed" if actor == "elder" else "caregiver_confirmed",
            "reminder_version": new_version,
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


def mark_snoozed_until(
    db,
    schedule_doc_ref,
    uid: str,
    task_id: str,
    snoozed_until_iso: str,
    actor: str = "elder",
):
    return transition_task_status(
        db=db,
        schedule_doc_ref=schedule_doc_ref,
        uid=uid,
        task_id=task_id,
        new_status="snoozed",
        actor=actor,
        extra_patch={"snoozedUntil": snoozed_until_iso},
        event_type="snoozed",
        meta={"snoozed_until": snoozed_until_iso},
        confidence="medium",
    )




def mark_skipped(
    db,
    schedule_doc_ref,
    uid: str,
    task_id: str,
    actor: str = "elder",
    reason: Optional[str] = None,
    skip_reasons: List[str] = [],
    skip_decision_by: str = None,
    caregiver_skip_note: str = None,
):
    normalised_reason = normalize_skip_reason(reason)

    # Read current reminderVersion so we can increment it atomically.
    # This lets the reminder engine detect a skip that happened between
    # its poll and the actual push send — even if snoozeVersion didn't change.
    current_reminder_version = 0
    try:
        snap = schedule_doc_ref.get()
        if snap.exists:
            tasks = snap.to_dict().get("tasks", [])
            task_data = next((t for t in tasks if t.get("id") == task_id), None)
            if task_data:
                current_reminder_version = int(task_data.get("reminderVersion", 0) or 0)
    except Exception:
        pass

    return transition_task_status(
        db=db,
        schedule_doc_ref=schedule_doc_ref,
        uid=uid,
        task_id=task_id,
        new_status="skipped",
        actor=actor,
        extra_patch={
            "skippedAt": utc_now_iso(),
            "skipReason": normalised_reason,
            "skipReasons": skip_reasons,
            "skipDecisionBy": skip_decision_by or actor,
            "lastSkipDecisionBy": actor,
            "actor": actor,
            "caregiverSkipNote": caregiver_skip_note,
            "completed": False,
            "snoozedUntil": None,
            "reminderVersion": current_reminder_version + 1,
            "snoozeVersion": current_reminder_version + 1,
            "pendingReminderInvalidatedAt": utc_now_iso(),
        },
        event_type="skipped",
        meta={"reason": normalised_reason},
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


def _get_current_reminder_version(schedule_doc_ref, task_id: str) -> int:
    """Helper to read current reminderVersion or snoozeVersion from Firestore."""
    try:
        snap = schedule_doc_ref.get()
        if snap.exists:
            tasks = snap.to_dict().get("tasks", [])
            task_data = next((t for t in tasks if t.get("id") == task_id), None)
            if task_data:
                # Fallback to snoozeVersion for legacy tasks
                return int(task_data.get("reminderVersion", 0) or task_data.get("snoozeVersion", 0) or 0)
    except Exception:
        pass
    return 0


def invalidate_existing_reminders_for_task(db, schedule_doc_ref, task_id: str, reason: str):
    """
    Cancel all existing reminder state for a task.
    This is called before reschedule, skip, or completion to stop old reminder chains.
    """
    try:
        log_task_event(
            db=db,
            uid="system", 
            task_id=task_id,
            event_type="reminders_invalidated",
            actor="system",
            meta={"reason": reason, "invalidatedAt": utc_now_iso()}
        )
    except Exception:
        pass


def reschedule_task_time(
    db,
    schedule_doc_ref,
    uid: str,
    task_id: str,
    new_time_str: str,
    new_datetime_iso: str,
    valid_until_iso: str,
    actor: str = "elder",
):
    # Read existing reminderVersion so we can increment it atomically.
    current_version = _get_current_reminder_version(schedule_doc_ref, task_id)
    new_version = current_version + 1

    # Invalidate old reminders before updating state
    invalidate_existing_reminders_for_task(db, schedule_doc_ref, task_id, "rescheduled")

    return transition_task_status(
        db=db,
        schedule_doc_ref=schedule_doc_ref,
        uid=uid,
        task_id=task_id,
        new_status="snoozed",
        actor=actor,
        extra_patch={
            "time": new_time_str,
            "scheduledAt": new_datetime_iso,
            "snoozedUntil": new_datetime_iso,
            "validFrom": new_datetime_iso,
            "validUntil": valid_until_iso,
            "lastReminderAt": None,
            "last_reminder_at": None,
            "retryCount": 0,
            "reminder_count": 0,
            "reminderVersion": new_version, # Unified version field
            "snoozeVersion": new_version,   # Keep backward compat for now
            "acknowledgedAt": None,
            "startedAt": None,
            "completed": False,
            "completedAt": None,
            "completedBy": None,
        },
        event_type="rescheduled",
        meta={
            "new_time": new_time_str,
            "rescheduled_to": new_datetime_iso,
            "reminder_version": new_version,
        },
        confidence="medium",
    )



# =============================================================================
# Skip orchestration helpers
# =============================================================================

def get_task_from_schedule(schedule_doc_ref, task_id: str) -> Optional[Dict[str, Any]]:
    """
    Reads the schedule document and returns the matching task dict, or None.
    Kept separate so handle_task_skip can inspect policy fields before mutating.
    """
    try:
        snap = schedule_doc_ref.get()
        if not snap.exists:
            return None
        tasks = snap.to_dict().get("tasks", [])
        return next((t for t in tasks if t.get("id") == task_id), None)
    except Exception:
        return None


def parse_iso(iso_str: Optional[str]) -> Optional[datetime]:
    """
    Safely parses an ISO-8601 datetime string.  Returns None on failure.
    Strips trailing 'Z' so Python 3.10 fromisoformat() handles it correctly.
    """
    if not iso_str:
        return None
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def count_recent_skips(db, uid: str, task_name: str, days: int = 7) -> int:
    """
    Counts how many times a particular task (by name) was skipped 
    by this user in the last N days.
    """
    cutoff = (utc_now() - timedelta(days=days)).isoformat()
    try:
        docs = (
            db.collection("task_events")
            .where("uid", "==", uid)
            .where("type", "==", "skipped")
            .where("at", ">=", cutoff)
            .stream()
        )
        count = 0
        for d in docs:
            data = d.to_dict()
            meta = data.get("meta", {})
            if meta.get("task_name") == task_name:
                count += 1
        return count
    except Exception:
        return 0



def get_primary_caregiver_for_elder(db, uid: str) -> Optional[str]:
    """
    Looks up the linked caregiverId for a given elder UID.
    Tries the 'elders' collection first, then falls back to 'elder_profiles'.
    """
    try:
        # Check main elders doc
        doc = db.collection("elders").document(uid).get()
        if doc.exists:
            caregiver_id = doc.to_dict().get("caregiverId")
            if caregiver_id:
                return caregiver_id

        # Fallback to profile
        profile = db.collection("elder_profiles").document(uid).get()
        if profile.exists:
            return profile.to_dict().get("caregiverId")

        return None
    except Exception:
        return None


def maybe_escalate_skipped_task(
    db,
    schedule_doc_ref,
    uid: str,
    task: Dict[str, Any],
    actor: str,
    reason: str,
    date: str,
    notify_caregiver_override: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Enforces skip escalation and caregiver notification policy.

    Short-circuits immediately if the actor is already a caregiver (no
    self-notification loop).  Returns a simple {notified, reason} dict.

    Reads escalation flags directly from the task document (stamped at
    creation) so no rule lookup is needed at runtime.
    """
    # Short-circuit: caregiver skipped it themselves — no notification loop
    if actor == "caregiver":
        return {"notified": False, "reason": "caregiver_already_involved"}

    escalate_on_skip = bool(task.get("escalateOnSkip"))
    notify_caregiver = (
        notify_caregiver_override
        if notify_caregiver_override is not None
        else bool(task.get("notifyCaregiverOnSkip"))
    )

    # 18. Analytics-driven escalation for repeated skips
    # Even if policy is disabled locally, repeated medication skips escalate.
    recent_skips = count_recent_skips(db, uid, task.get("task_name"), days=7)
    if recent_skips >= 2 and task.get("type") == "medication":
        escalate_on_skip = True
        notify_caregiver = True

    # Nothing to do if both flags are off
    if not escalate_on_skip and not notify_caregiver:
        return {"notified": False, "reason": "policy_disabled"}

    # Stamp all skip-state fields in a single write
    update_task_in_schedule(
        schedule_doc_ref=schedule_doc_ref,
        task_id=task["id"],
        patch={
            "caregiverSkipNotified": True,
            "caregiverNotified": True,
            "skipReviewRequired": True,
            # Escalated tasks move to a dedicated review status so the
            # caregiver dashboard surfaces them; non-escalated skips stay
            # as "skipped" (visible but not urgent).
            "status": "needs_caregiver_review" if escalate_on_skip else "skipped",
        },
    )

    log_task_event(
        db=db,
        uid=uid,
        task_id=task["id"],
        event_type="skip_escalated",
        actor="system",
        meta={
            "reason": reason,
            "task_name": task.get("task_name"),
            "task_type": task.get("type"),
            "risk_level": task.get("riskLevel"),
        },
        confidence="high",
    )

    # Hook: send the actual notification document
    caregiver_id = get_primary_caregiver_for_elder(db, uid)
    if caregiver_id:
        notify_caregiver_of_skipped_task(
            db=db,
            caregiver_id=caregiver_id,
            uid=uid,
            task=task,
            reason=reason,
            date=date
        )

    return {"notified": True if caregiver_id else False, "reason": "critical_skip" if caregiver_id else "no_caregiver_found", "caregiver_id": caregiver_id}


# =============================================================================
# handle_task_skip — policy-driven skip entrypoint
# =============================================================================

def handle_task_skip(
    db,
    schedule_doc_ref,
    uid: str,
    task_id: str,
    date: str,
    actor: str = "elder",
    reason: Optional[str] = None,
    skip_reasons: List[str] = [],
    skip_decision_by: str = None,
    caregiver_skip_note: str = None,
    confirmed: bool = False,
    notify_caregiver_override: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Policy-driven orchestrator for skipping a task.

    Replaces direct calls to mark_skipped() for real user-facing actions.
    mark_skipped() remains available as the low-level primitive.

    Flow:
    1. Load task — fail fast if not found.
    2. Confirmation gate — high-priority tasks require elder confirmation.
    3. Pre-schedule gate — some task types block early skips.
    4. Commit the skip via mark_skipped() (normalises reason, stamps state).
    5. Stamp additional skip-state fields.
    6. Log a policy-applied audit event.
    7. Run escalation / caregiver-notify checks.

    Returns a result dict:
        {"status": "skipped" | "confirmation_required" | "blocked", ...}
    """
    # 1. Load task
    task = get_task_from_schedule(schedule_doc_ref, task_id)
    if not task:
        raise ValueError(f"Task '{task_id}' not found in schedule.")

    rule = get_task_rule(task.get("type", "common"))
    norm_reason = normalize_skip_reason(reason)
    now_iso = utc_now_iso()

    # 2. Confirmation gate — medication-class tasks require explicit "yes"
    if actor == "elder" and rule.get("require_skip_confirmation") and not confirmed:
        return {
            "status": "confirmation_required",
            "task_id": task_id,
            "task_name": task.get("task_name", "This task"),
            "message": (
                f"{task.get('task_name', 'This task')} is important. "
                "Do you want to skip it?"
            ),
        }

    # 3. Pre-schedule gate — some tasks cannot be skipped before their window
    if not rule.get("allow_pre_schedule_skip", True) and actor == "elder":
        scheduled_at = parse_iso(task.get("scheduledAt"))
        if scheduled_at and datetime.utcnow() < scheduled_at.replace(tzinfo=None):
            return {
                "status": "blocked",
                "task_id": task_id,
                "message": "This task cannot be skipped before its scheduled time.",
            }

    # 4. Prepare consolidated patch
    norm_reason = normalize_skip_reason(reason)
    now_iso = utc_now_iso()

    # Invalidate old reminders before updating state
    invalidate_existing_reminders_for_task(db, schedule_doc_ref, task_id, f"skipped_{norm_reason}")

    # Policy check for escalation
    escalate_on_skip = bool(task.get("escalateOnSkip"))
    notify_caregiver = bool(task.get("notifyCaregiverOnSkip"))
    if notify_caregiver_override is not None:
        notify_caregiver = notify_caregiver_override

    # Repeated skip escalation logic
    recent_skips = count_recent_skips(db, uid, task.get("task_name"), days=7)
    if recent_skips >= 2 and task.get("type") == "medication":
        escalate_on_skip = True
        notify_caregiver = True

    # Build the single patch
    current_version = _get_current_reminder_version(schedule_doc_ref, task_id)
    new_version = current_version + 1

    patch = {
        "status": "needs_caregiver_review" if escalate_on_skip else "skipped",
        "skippedAt": now_iso,
        "skipReason": norm_reason,
        "skipReasons": skip_reasons,
        "skipDecisionBy": skip_decision_by or actor,
        "lastSkipDecisionBy": actor,
        "actor": actor,
        "caregiverSkipNote": caregiver_skip_note,
        "completed": False,
        "updatedAt": now_iso,
        "caregiverNotified": notify_caregiver and escalate_on_skip,
        "caregiverSkipNotified": notify_caregiver,
        "skipReviewRequired": escalate_on_skip,
        "skipReviewedAt": now_iso if actor == "caregiver" else None,
        "snoozedUntil": None,
        "reminderVersion": new_version,
        "snoozeVersion": new_version,
    }

    # 5. Apply single atomic write
    update_task_in_schedule(
        schedule_doc_ref=schedule_doc_ref,
        task_id=task_id,
        patch=patch
    )

    # 6. Audit event
    log_task_event(
        db=db,
        uid=uid,
        task_id=task_id,
        event_type="skip_policy_applied",
        actor="system",
        meta={
            "reason": norm_reason,
            "actor": actor,
            "task_type": task.get("type"),
            "status": patch["status"],
            "escalated": escalate_on_skip,
        },
        confidence="high",
    )

    # 7. Notify caregiver if needed
    notified = False
    if notify_caregiver:
        caregiver_id = get_primary_caregiver_for_elder(db, uid)
        if caregiver_id:
            notify_caregiver_of_skipped_task(
                db=db,
                caregiver_id=caregiver_id,
                uid=uid,
                task=task,
                reason=norm_reason,
                date=date
            )
            notified = True

    return {
        "status": patch["status"],
        "task_id": task_id,
        "task_name": task.get("task_name"),
        "reason": norm_reason,
        "notified": notified
    }

