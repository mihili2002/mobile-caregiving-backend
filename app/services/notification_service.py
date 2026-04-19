# app/services/notification_service.py

import os
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