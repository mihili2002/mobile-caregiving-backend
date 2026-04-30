# app/services/notification_service.py

import os
from datetime import datetime
from firebase_admin import messaging
from app.services.logger import log_debug

def send_voice_reminder_notification(token: str, message_text: str, audio_url: str, category: str):
    """
    Sends a data message via FCM to trigger a voice reminder on the mobile app.
    """
    try:
        message = messaging.Message(
            data={
                "type": "VOICE_REMINDER",
                "messageText": message_text,
                "audioUrl": audio_url,
                "category": category,
            },
            token=token,
        )
        response = messaging.send(message)
        log_debug("fcm_sent", {"response": response, "message": message_text})
        return True
    except Exception as e:
        log_debug("fcm_error", {"error": str(e), "message": message_text})
        return False


def notify_caregiver_of_skipped_task(db, caregiver_id: str, uid: str, task: dict, reason: str, date: str):
    """
    Creates an in-app notification document for the caregiver in Firestore.
    """
    try:
        notification_payload = {
            "type": "task_skipped",
            "elderUid": uid,
            "taskId": task.get("id"),
            "taskName": task.get("task_name"),
            "taskType": task.get("type"),
            "reason": reason,
            "status": task.get("status") or "needs_caregiver_review",
            "date": date,
            "createdAt": datetime.utcnow().isoformat(),
            "needsReview": True,
            "reviewedAt": None,
        }

        # Add to caregiver's notifications sub-collection
        db.collection("users").document(caregiver_id).collection("notifications").add(notification_payload)
        log_debug("caregiver_notified_on_skip", {"caregiver_id": caregiver_id, "elder_uid": uid})
        return True
    except Exception as e:
        log_debug("caregiver_notify_error", {"error": str(e), "elder_uid": uid})
        return False