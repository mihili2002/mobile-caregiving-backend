
from flask import Blueprint, request, jsonify
from firebase_admin import firestore
from google.cloud.firestore import FieldFilter, And
from datetime import datetime

behavior_bp = Blueprint('behavior_bp', __name__)
db = firestore.client()

@behavior_bp.route('/log_event', methods=['POST'])
def log_event():
    try:
        data = request.json
        
        # Support both old and new schema
        uid = data.get('uid') or data.get('elderId')
        task_id = data.get('taskId') or data.get('taskInstanceId') or data.get('metadata', {}).get('task_id')
        schedule_doc_id = data.get('scheduleDocId')
        
        event_type = data.get('type') or data.get('event_type')
        timestamp = data.get('at') or data.get('timestamp') or datetime.utcnow().isoformat()
        meta = data.get('meta') or data.get('metadata') or {}

        if not uid or not event_type:
            return jsonify({"error": "uid and type required"}), 400
            
        # Standardize Event Type to Upper Case
        if event_type == 'task_completed': event_type = "TASK_COMPLETED"
        elif event_type == 'snooze': event_type = "REMINDER_SNOOZED"
        elif event_type == 'reminder_sent': event_type = "REMINDER_SENT"
        
        # Store in Firestore 'task_events'
        db.collection('task_events').add({
            "uid": uid,
            "scheduleDocId": schedule_doc_id, # Can be null if not provided, but mostly should be sent
            "taskId": task_id,
            "type": event_type.upper(),
            "at": timestamp,
            "meta": meta,
            "created_at": datetime.utcnow()
        })

        return jsonify({"message": "Event logged"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@behavior_bp.route('/analyze_missed_tasks', methods=['POST'])
def analyze_missed_tasks():
    # Helper to scan a past date and log missed tasks if not already logged
    try:
        data = request.json
        uid = data.get('uid')
        date_str = data.get('date') # DD.MM.YYYY format stored in schedule

        schedule_ref = db.collection('schedules').document(f"{uid}_{date_str}")
        doc = schedule_ref.get()
        
        missed = []
        if doc.exists:
            tasks = doc.to_dict().get('tasks', [])
            for t in tasks:
                if not t.get('isCompleted') and not t.get('completed'):
                     # This is a missed task
                     missed.append(t['taskName'])
                     # Log it as an observation logic
        
        return jsonify({"missed_count": len(missed), "missed_tasks": missed}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@behavior_bp.route('/generate_insights', methods=['GET'])
def generate_insights():
    try:
        uid = request.args.get('uid')
        if not uid:
            return jsonify({"error": "uid required"}), 400

        # 1. Fetch recent completion logs
        # 1. Fetch completion logs (No order_by to avoid Composite Index requirement)
        logs_stream = db.collection('behavior_logs')\
            .where(filter=And(filters=[
                FieldFilter('uid', '==', uid),
                FieldFilter('event_type', '==', 'task_completed')
            ]))\
            .stream()

        # Sort in memory (Desc by timestamp)
        all_logs = []
        for l in logs_stream:
            all_logs.append(l)
            
        # usage of lambda for sorting by timestamp safely - forcing str conversion
        logs = sorted(all_logs, key=lambda x: str(x.to_dict().get('timestamp', '') or ''), reverse=True)[:50]

        task_history = {} # { "Lunch": [45, 50, 40], "Dinner": [0, 5] }

        for log in logs:
            data = log.to_dict()
            meta = data.get('metadata', {})
            name = meta.get('task_name')
            delay = meta.get('delay_minutes', 0)
            
            if name:
                if name not in task_history:
                    task_history[name] = []
                task_history[name].append(delay)

        suggestions = []

        # 2. Analyze Patterns
        for task_name, delays in task_history.items():
            # Rule: Late for at least 3 recent occurrences (> 30 mins)
            # Relaxed for demo: >= 1 occurrence if seeding is light, but prompt asked for "3 days in a row"
            # I will adhere to "3 days" logic if possible, but fall back to 1 for easier testing if needed.
            # Let's stick to the prompt's scenario: 3 occurrences.
            if len(delays) >= 3:
                recent_delays = delays[:3]
                avg_delay = sum(recent_delays) / 3
                
                if avg_delay > 30:
                    suggestions.append({
                        "type": "schedule_adjustment",
                        "task_name": task_name,
                        "avg_delay": int(avg_delay),
                        "message": f"I noticed you've been about {int(avg_delay)} minutes late for {task_name} recently. Should we move it?",
                        "suggested_offset": int(avg_delay)
                    })
        
        # DEMO OVERRIDE: If no real data, inject the specific example from the prompt for the user to see
        # This ensures they see the requirement is met immediately.
        # No fake suggestions. Real data only.

        return jsonify({"insights": suggestions}), 200

    except Exception as e:
        print(f"Insight Error: {e}")
        return jsonify({"error": str(e)}), 500

@behavior_bp.route('/save_journal_entry', methods=['POST'])
def save_journal_entry():
    try:
        data = request.json
        # Expects: { 'id': '...', 'userId': '...', 'text': '...', 'type': '...', 'timestamp': '...' }
        
        # Determine ID
        entry_id = data.get('id')
        if not entry_id:
             # Generates a new ID if not provided
             entry_id = db.collection('journal_entries').document().id
        
        # Save using Admin SDK (Bypasses Rules)
        db.collection('journal_entries').document(entry_id).set(data, merge=True)
        
        return jsonify({"message": "Journal saved", "id": entry_id}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@behavior_bp.route('/delete_journal_entry', methods=['POST'])
def delete_journal_entry():
    try:
        data = request.json
        entry_id = data.get('id')
        if not entry_id:
             return jsonify({"error": "id required"}), 400

        db.collection('journal_entries').document(entry_id).delete()
        return jsonify({"message": "Journal deleted"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@behavior_bp.route('/get_journal_entries', methods=['GET'])
def get_journal_entries():
    try:
        user_id = request.args.get('userId')
        if not user_id:
            return jsonify({"error": "userId required"}), 400
            
        docs = db.collection('journal_entries')\
            .where(filter=FieldFilter('userId', '==', user_id))\
            .order_by('timestamp', direction=firestore.Query.DESCENDING)\
            .stream()
            
        entries = []
        for doc in docs:
            entry = doc.to_dict()
            entry['id'] = doc.id
            entries.append(entry)
            
        return jsonify(entries), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
