from fastapi import APIRouter, HTTPException, BackgroundTasks, Response
from fastapi.responses import FileResponse # Kept import just in case, though unused
import os
from app.services.voice_service import voice_service
from app.core.firebase import get_db

router = APIRouter(prefix="/api/audio", tags=["Audio"])

@router.get("/{uid}/{task_id}")
async def get_voice_reminder(uid: str, task_id: str, forgotten: bool = False):
    """
    Endpoint to generate and serve a voice reminder for a specific task.
    """
    db = get_db()
    # 1. Fetch task details to get the name and category
    from datetime import datetime
    today_iso = datetime.now().strftime("%Y-%m-%d")
    
    from google.cloud.firestore_v1.base_query import FieldFilter
    
    schedules = db.collection('schedules').where(filter=FieldFilter('uid', '==', uid)).where(filter=FieldFilter('date', '==', today_iso)).limit(1).stream()
    
    task_data = None
    for doc in schedules:
        tasks = doc.to_dict().get('tasks', [])
        for t in tasks:
            if str(t.get('id')) == task_id or t.get('taskId') == task_id:
                task_data = t
                break
        if task_data: break
    
    if not task_data:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task_name = task_data.get('task_name') or task_data.get('taskName') or "task"
    category = "urgent" if forgotten else (task_data.get('type') or 'common')
    
    if forgotten:
        text = f"Pardon me, it seems you have forgotten to {task_name}. Please try to complete it at least now."
    else:
        text = f"Reminder, it is time for {task_name}."
    
    # Generate audio directly in memory using the new service signature
    audio_bytes = voice_service.generate_voice_reminder(text, category, forgotten=forgotten)
    
    if audio_bytes:
        return Response(content=audio_bytes, media_type="audio/mpeg")
    else:
        raise HTTPException(status_code=500, detail="Failed to generate voice reminder")

@router.get("/generate")
async def generate_voice_from_text(text: str, category: str = "common", forgotten: bool = False):
    """
    General purpose endpoint to generate voice audio from raw text.
    Used by the frontend for dynamic alerts and custom messages.
    """
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")
        
    # Auto-infer category if it's generic to ensure correct voice profile
    text_l = text.lower()
    if category == "common":
        if any(word in text_l for word in ["nap", "sleep", "rest", "leisure"]):
            category = "leisure"
        elif any(word in text_l for word in ["medicine", "pill", "pill", "tablet", "health", "doctor"]):
            category = "medication"
        elif any(word in text_l for word in ["meal", "breakfast", "lunch", "dinner", "snack"]):
            category = "meal"
        elif any(word in text_l for word in ["exercise", "therapy", "breathing", "walk"]):
            category = "therapy"
        elif any(word in text_l for word in ["call", "visit", "friend", "social"]):
            category = "social"

    # Generate audio directly in memory using the new service signature
    audio_bytes = voice_service.generate_voice_reminder(text, category, forgotten=forgotten)
    
    if audio_bytes:
        return Response(content=audio_bytes, media_type="audio/mpeg")
    else:
        raise HTTPException(status_code=500, detail="Failed to generate voice audio")
