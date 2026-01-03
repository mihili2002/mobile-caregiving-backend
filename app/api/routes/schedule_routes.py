from flask import Blueprint, request, jsonify
from firebase_admin import firestore
import uuid
from datetime import datetime

schedule_bp = Blueprint('schedule_bp', __name__)
db = firestore.client()

from app.services.time_utils import get_schedule_doc_id

@schedule_bp.route('/get_schedule', methods=['POST'])
def get_schedule():
    try:
        data = request.json
        uid = data.get('uid')
        date = data.get('date') # YYYY-MM-DD

        if not uid or not date:
            return jsonify({"error": "uid and date required"}), 400

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
                    # New Fields
                    "scheduledAt": t.get('scheduledAt') or t.get('scheduledTime'),
                    "completedAt": t.get('completedAt') or t.get('completedTime'),
                    "status": t.get('status', 'scheduled'),
                    "graceMinutes": t.get('graceMinutes', 30)
                })
            
            return jsonify({
                "userId": uid,
                "date": date,
                "status": data.get('status', 'active'),
                "tasks": mapped_tasks
            }), 200
        else:
            # Return empty skeleton if no schedule exists yet
            return jsonify({
                "userId": uid,
                "date": date,
                "status": "active",
                "tasks": []
            }), 200

    except Exception as e:
        print(f"Error in /get_schedule: {e}")
        return jsonify({"error": str(e)}), 500

@schedule_bp.route('/add_task', methods=['POST'])
def add_task_to_schedule():
    try:
        data = request.json
        uid = data.get('uid')
        date = data.get('date')
        task_data = data.get('task') # { "task_name": "...", "time": "...", "type": "..." }

        if not uid or not date or not task_data:
            return jsonify({"error": "uid, date, and task required"}), 400

        doc_id = get_schedule_doc_id(uid, date)
        doc_ref = db.collection('schedules').document(doc_id)

        # Map to Request Schema (Exact Match)
        firestore_task = {
            "id": task_data.get('id') or str(uuid.uuid4()),
            "task_name": task_data.get('task_name'),
            "time": task_data.get('time'),
            "type": task_data.get('type', 'common'),
            "completed": task_data.get('completed', False),
            "completedAt": task_data.get('completedAt') or None,
            
            # Additional Metadata (Optional but good to keep under these keys)
            "scheduledAt": task_data.get('scheduledAt'), 
            "graceMinutes": task_data.get('graceMinutes', 30),
            
            # Legacy/Alternate Keys (Keep for safety if needed, or rely on mapper)
            # "taskId": ... (removed to strictly follow schema)
        }

        # Handle Document & Task Insertion
        doc = doc_ref.get()
        if not doc.exists:
            doc_ref.set({
                "userId": uid,  # Requested Key
                "date": date,   # YYYY-MM-DD (or keep stored format, user requested '2025-12-24')
                # Storing date as requested format YYYY-MM-DD is cleaner, but let's see if get_doc_id expects conversion.
                # get_doc_id uses DD.MM.YYYY internally for ID, but let's store standard ISO in body.
                "status": "active", # Requested Key
                "tasks": [firestore_task],
                "created_at": datetime.utcnow().isoformat(),
                
                # Legacy support
                "uid": uid 
            })
        else:
            doc_ref.update({
                "tasks": firestore.ArrayUnion([firestore_task])
            })

        return jsonify({"message": "Task added", "task": task_data}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@schedule_bp.route('/update_task_status', methods=['POST'])
def update_task_status():
    try:
        data = request.json
        uid = data.get('uid')
        date = data.get('date')
        task_id = data.get('task_id')
        is_completed = data.get('completed') # boolean

        if not uid or not date or not task_id:
            return jsonify({"error": "uid, date, and task_id required"}), 400

        doc_id = get_schedule_doc_id(uid, date)
        doc_ref = db.collection('schedules').document(doc_id)
        
        doc = doc_ref.get()
        if not doc.exists:
            return jsonify({"error": "Schedule not found"}), 404

        schedule_data = doc.to_dict()
        tasks = schedule_data.get('tasks', [])
        
        updated = False
        for t in tasks:
            # Check both key variants (Priority: id)
            tid = t.get('id') or t.get('taskId')
            if tid == task_id:
                # Update requested field
                t['completed'] = is_completed
                
                # --- PHASE 1 & Refactor: Update Behavior Fields ---
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
            return jsonify({"message": "Task updated"}), 200
        else:
            return jsonify({"error": "Task not found"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@schedule_bp.route('/delete_task', methods=['POST'])
def delete_task():
    try:
        data = request.json
        uid = data.get('uid')
        date = data.get('date')
        task_id = data.get('task_id')

        if not uid or not date or not task_id:
            return jsonify({"error": "uid, date, and task_id required"}), 400

        doc_id = get_schedule_doc_id(uid, date)
        doc_ref = db.collection('schedules').document(doc_id)
        
        doc = doc_ref.get()
        if not doc.exists:
            return jsonify({"error": "Schedule not found"}), 404

        schedule_data = doc.to_dict()
        tasks = schedule_data.get('tasks', [])
        
        new_tasks = [t for t in tasks if (t.get('taskId') or t.get('id')) != task_id]
        
        if len(new_tasks) < len(tasks):
            doc_ref.update({"tasks": new_tasks})
            return jsonify({"message": "Task deleted"}), 200
        else:
            return jsonify({"error": "Task not found"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@schedule_bp.route('/update_task', methods=['POST'])
def update_task_details():
    try:
        data = request.json
        uid = data.get('uid')
        date = data.get('date')
        task_id = data.get('task_id')
        updates = data.get('updates') # { "time": "...", "task_name": "..." }

        if not uid or not date or not task_id or not updates:
            return jsonify({"error": "uid, date, task_id, and updates required"}), 400

        doc_id = get_schedule_doc_id(uid, date)
        doc_ref = db.collection('schedules').document(doc_id)
        
        doc = doc_ref.get()
        if not doc.exists:
            return jsonify({"error": "Schedule not found"}), 404

        schedule_data = doc.to_dict()
        tasks = schedule_data.get('tasks', [])
        
        updated = False
        for t in tasks:
            tid = t.get('id') or t.get('taskId')
            if tid == task_id:
                # Update allowed fields (Schema Keys)
                if 'time' in updates:
                     t['time'] = updates['time'] 
                if 'task_name' in updates:
                     t['task_name'] = updates['task_name']
                updated = True
                break
        
        if updated:
            doc_ref.update({"tasks": tasks})
            return jsonify({"message": "Task updated"}), 200
        else:
            return jsonify({"error": "Task not found"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@schedule_bp.route('/complete', methods=['POST'])
def complete_task():
    try:
        data = request.json
        uid = data.get('uid')
        date = data.get('date') # YYYY-MM-DD
        task_id = data.get('taskId')
        
        if not all([uid, date, task_id]):
            return jsonify({"error": "uid, date, taskId required"}), 400

        doc_id = get_schedule_doc_id(uid, date)
        doc_ref = db.collection('schedules').document(doc_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            return jsonify({"error": "Schedule not found"}), 404
            
        t_data = doc.to_dict()
        tasks = t_data.get('tasks', [])
        
        target_task = None
        updated = False
        
        # 1. Update Task in Array
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
            return jsonify({"error": "Task not found"}), 404
            
        # 2. Save Schedule
        doc_ref.update({"tasks": tasks})
        
        # 3. Calculate Delay
        delay = 0
        scheduled_at = target_task.get('scheduledAt')
        scheduled_time_str = target_task.get('scheduledTime') # "12:00"
        
        try:
            now_dt = datetime.utcnow()
            if scheduled_at:
                sch_dt = datetime.fromisoformat(scheduled_at)
                delay = int((now_dt - sch_dt).total_seconds() / 60)
            elif scheduled_time_str:
                pass 
        except:
            pass
            
        # 4. Log Event (Backend Side)
        try:
            db.collection('task_events').add({
                "uid": uid,
                "scheduleDocId": doc_id,
                "taskId": task_id,
                "type": "TASK_COMPLETED",
                "at": datetime.utcnow().isoformat(),
                "meta": {
                    "task_name": target_task.get('taskName'),
                    "category": target_task.get('category', 'common'),
                    "scheduled_at": scheduled_at,
                    "scheduled_time": scheduled_time_str,
                    "delay_minutes": max(0, delay),
                    "source": "backend_endpoint"
                },
                "created_at": datetime.utcnow()
            })
            
            # --- CONNECTION TO AI MEMORY ---
            # Allows user to ask "Did I take my meds?" and AI finds this event.
            try:
                from app.services.memory_engine import memory_engine
                mem_text = f"I completed the task '{target_task.get('task_name', 'unknown')}'."
                memory_engine.store_memory(mem_text, {
                    "uid": uid,
                    "type": "task_completion_ui",
                    "category": target_task.get('category', 'common'),
                    "timestamp": datetime.now().isoformat() 
                })
            except Exception as mem_err:
                print(f"Failed to store memory: {mem_err}")
                
        except Exception as e:
            print(f"Failed to log completion event: {e}")

        return jsonify({"message": "Task completed", "completedAt": target_task['completedAt']}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
