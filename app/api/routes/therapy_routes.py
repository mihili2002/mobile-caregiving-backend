from flask import Blueprint, request, jsonify
from firebase_admin import firestore
import uuid
from datetime import datetime

therapy_bp = Blueprint('therapy_bp', __name__)
db = firestore.client()

@therapy_bp.route('/save_recommendation', methods=['POST'])
def save_recommendation():
    try:
        data = request.json
        elder_id = data.get('elder_id')
        activity_name = data.get('activity_name')
        
        # Optional fields
        duration = data.get('duration', '30 mins')
        instructions = data.get('instructions', '')
        assigned_by = data.get('assigned_by', 'Therapist')

        if not elder_id or not activity_name:
            return jsonify({"error": "elder_id and activity_name are required"}), 400

        doc_ref = db.collection('therapy_assignments').document()
        
        assignment_data = {
            "id": doc_ref.id,
            "elder_id": elder_id,
            "activity_name": activity_name,
            "duration": duration,
            "instructions": instructions,
            "assigned_by": assigned_by,
            "date_assigned": datetime.utcnow().isoformat(),
            "is_active": True,
            "type": "therapist" # Align with aggregator
        }
        
        doc_ref.set(assignment_data)

        return jsonify({"message": "Recommendation saved", "id": doc_ref.id, "data": assignment_data}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500
