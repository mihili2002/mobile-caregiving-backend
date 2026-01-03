from fastapi import APIRouter, Request, HTTPException, Body
from pydantic import BaseModel
from firebase_admin import firestore
import uuid
from datetime import datetime
from typing import Optional, List, Any

from app.services.time_utils import get_schedule_doc_id

router = APIRouter(prefix="/api/schedule", tags=["schedule"])

class GetScheduleRequest(BaseModel):
    uid: str
    date: str  # YYYY-MM-DD

class TaskData(BaseModel):
    id: Optional[str] = None
    task_name: str
    time: str
    type: Optional[str] = "common"
    completed: Optional[bool] = False
    completedAt: Optional[str] = None
    scheduledAt: Optional[str] = None
    graceMinutes: Optional[int] = 30

class AddTaskRequest(BaseModel):
    uid: str
    date: str
    task: TaskData

class UpdateTaskStatusRequest(BaseModel):
    uid: str
    date: str
    task_id: str
    completed: bool

class UpdateTaskRequest(BaseModel):
    uid: str
    date: str
    task_id: str
    updates: dict

class CompleteTaskRequest(BaseModel):
    uid: str
    date: str
    taskId: str

@router.post("/get_schedule")
async def get_schedule(req: GetScheduleRequest):
    try:
        db = firestore.client()
        uid = req.uid
        date = req.date

        doc_id = get_schedule_doc_id(uid, date)
        doc_ref = db.collection('schedules').document(doc_id)
        doc = doc_ref.get()

        if doc.exists:
            data = doc.to_dict()
            tasks = data.get('tasks', [])
            mapped_tasks = []
            for t in tasks:
                mapped_tasks.append({
                    "id": t.get('taskId') or t.get('id') or str(uuid.uuid4()),
                    "task_name": t.get('taskName') or t.get('task_name'),
                    "time": t.get('Time') or t.get('time'),
                    "completed": t.get('isCompleted') if 'isCompleted' in t else t.get('completed', False),
                    "type": t.get('Type') or t.get('type', 'common'),
                    "task_number": t.get('taskNumber') or t.get('task_number'),
                    "scheduledAt": t.get('scheduledAt') or t.get('scheduledTime'),
                    "completedAt": t.get('completedAt') or t.get('completedTime'),
                    "status": t.get('status', 'scheduled'),
                    "graceMinutes": t.get('graceMinutes', 30)
                })
            
            return {
                "userId": uid,
                "date": date,
                "status": data.get('status', 'active'),
                "tasks": mapped_tasks
            }
        else:
            return {
                "userId": uid,
                "date": date,
                "status": "active",
                "tasks": []
            }

    except Exception as e:
        print(f"Error in /get_schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/add_task")
async def add_task_to_schedule(req: AddTaskRequest):
    try:
        db = firestore.client()
        uid = req.uid
        date = req.date
        task_data = req.task.model_dump()

        doc_id = get_schedule_doc_id(uid, date)
        doc_ref = db.collection('schedules').document(doc_id)

        firestore_task = {
            "id": task_data.get('id') or str(uuid.uuid4()),
            "task_name": task_data.get('task_name'),
            "time": task_data.get('time'),
            "type": task_data.get('type', 'common'),
            "completed": task_data.get('completed', False),
            "completedAt": task_data.get('completedAt') or None,
            "scheduledAt": task_data.get('scheduledAt'), 
            "graceMinutes": task_data.get('graceMinutes', 30),
        }

        doc = doc_ref.get()
        if not doc.exists:
            doc_ref.set({
                "userId": uid,
                "date": date,
                "status": "active",
                "tasks": [firestore_task],
                "created_at": datetime.utcnow().isoformat(),
                "uid": uid 
            })
        else:
            doc_ref.update({
                "tasks": firestore.ArrayUnion([firestore_task])
            })

        return {"message": "Task added", "task": task_data}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/update_task_status")
async def update_task_status(req: UpdateTaskStatusRequest):
    try:
        db = firestore.client()
        uid = req.uid
        date = req.date
        task_id = req.task_id
        is_completed = req.completed

        doc_id = get_schedule_doc_id(uid, date)
        doc_ref = db.collection('schedules').document(doc_id)
        
        doc = doc_ref.get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Schedule not found")

        schedule_data = doc.to_dict()
        tasks = schedule_data.get('tasks', [])
        
        updated = False
        for t in tasks:
            tid = t.get('id') or t.get('taskId')
            if tid == task_id:
                t['completed'] = is_completed
                if is_completed:
                    t['status'] = 'completed'
                    t['completedAt'] = datetime.utcnow().isoformat()
                else:
                    t['status'] = 'scheduled'
                    t['completedAt'] = None
                updated = True
                break
        
        if updated:
            doc_ref.update({"tasks": tasks})
            return {"message": "Task updated"}
        else:
            raise HTTPException(status_code=404, detail="Task not found")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/delete_task")
async def delete_task(req: dict = Body(...)):
    # Use generic dict for simplicity or define DeleteTaskRequest
    try:
        db = firestore.client()
        uid = req.get('uid')
        date = req.get('date')
        task_id = req.get('task_id')

        if not uid or not date or not task_id:
            raise HTTPException(status_code=400, detail="uid, date, and task_id required")

        doc_id = get_schedule_doc_id(uid, date)
        doc_ref = db.collection('schedules').document(doc_id)
        
        doc = doc_ref.get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Schedule not found")

        schedule_data = doc.to_dict()
        tasks = schedule_data.get('tasks', [])
        
        new_tasks = [t for t in tasks if (t.get('taskId') or t.get('id')) != task_id]
        
        if len(new_tasks) < len(tasks):
            doc_ref.update({"tasks": new_tasks})
            return {"message": "Task deleted"}
        else:
            raise HTTPException(status_code=404, detail="Task not found")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/update_task")
async def update_task_details(req: UpdateTaskRequest):
    try:
        db = firestore.client()
        uid = req.uid
        date = req.date
        task_id = req.task_id
        updates = req.updates

        doc_id = get_schedule_doc_id(uid, date)
        doc_ref = db.collection('schedules').document(doc_id)
        
        doc = doc_ref.get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Schedule not found")

        schedule_data = doc.to_dict()
        tasks = schedule_data.get('tasks', [])
        
        updated = False
        for t in tasks:
            tid = t.get('id') or t.get('taskId')
            if tid == task_id:
                if 'time' in updates:
                     t['time'] = updates['time'] 
                if 'task_name' in updates:
                     t['task_name'] = updates['task_name']
                updated = True
                break
        
        if updated:
            doc_ref.update({"tasks": tasks})
            return {"message": "Task updated"}
        else:
            raise HTTPException(status_code=404, detail="Task not found")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/complete")
async def complete_task(req: CompleteTaskRequest):
    try:
        db = firestore.client()
        uid = req.uid
        date = req.date
        task_id = req.taskId
        
        doc_id = get_schedule_doc_id(uid, date)
        doc_ref = db.collection('schedules').document(doc_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Schedule not found")
            
        t_data = doc.to_dict()
        tasks = t_data.get('tasks', [])
        
        target_task = None
        updated = False
        
        for t in tasks:
            tid = t.get('id') or t.get('taskId')
            if tid == task_id:
                t['status'] = 'completed'
                now_iso = datetime.utcnow().isoformat()
                t['completedAt'] = now_iso
                t['completed'] = True 
                
                target_task = t
                updated = True
                break
        
        if not updated:
            raise HTTPException(status_code=404, detail="Task not found")
            
        doc_ref.update({"tasks": tasks})
        
        # Log event and store memory
        try:
            db.collection('task_events').add({
                "uid": uid,
                "scheduleDocId": doc_id,
                "taskId": task_id,
                "type": "TASK_COMPLETED",
                "at": datetime.utcnow().isoformat(),
                "meta": {
                    "task_name": target_task.get('task_name'),
                    "category": target_task.get('type', 'common'),
                    "source": "backend_endpoint"
                },
                "created_at": datetime.utcnow()
            })
            
            from app.services.memory_engine import memory_engine
            mem_text = f"I completed the task '{target_task.get('task_name', 'unknown')}'."
            memory_engine.store_memory(mem_text, {
                "uid": uid,
                "type": "task_completion_ui",
                "category": target_task.get('type', 'common'),
                "timestamp": datetime.now().isoformat() 
            })
        except Exception as e:
            print(f"Non-critical error in logging/memory: {e}")

        return {"message": "Task completed", "completedAt": target_task['completedAt']}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
