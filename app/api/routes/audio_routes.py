from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
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
    
    # Path to store audio
    temp_dir = os.path.join(os.getcwd(), "temp_audio")
    os.makedirs(temp_dir, exist_ok=True)
    audio_path = os.path.join(temp_dir, f"{uid}_{task_id}.mp3")

    # Only regenerate if the file doesn't already exist
    # This prevents Content-Length mismatch errors on range requests
    if not os.path.exists(audio_path):
        success = voice_service.generate_voice_reminder(text, category, audio_path)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to generate voice reminder")

    if not os.path.exists(audio_path):
        raise HTTPException(status_code=500, detail="Audio file not found after generation")

    return FileResponse(audio_path, media_type="audio/mpeg")
