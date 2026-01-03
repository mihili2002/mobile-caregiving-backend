from flask import Blueprint, request, jsonify
from firebase_admin import firestore
from datetime import datetime, timedelta
import re
from app.models.schemas import Medication

meds_bp = Blueprint('meds_bp', __name__)
db = firestore.client()

@meds_bp.route('/fix_permissions', methods=['POST'])
def fix_permissions():
    try:
        data = request.json
        print(f"DEBUG: Entered fix_permissions endpoint with data: {data}")
        elder_id = data.get('elder_id')
        caregiver_id = data.get('caregiver_id')
        
        if not elder_id or not caregiver_id:
            return jsonify({"error": "Missing elder_id or caregiver_id"}), 400

        # Use Admin SDK to bypass rules
        doc_ref = db.collection('elders').document(elder_id)
        # Verify if doc exists, if not create it with caregiverId
        # checking "exists" is theoretically redundant with merge=True set
        
        doc_ref.set({
            'caregiverId': caregiver_id
        }, merge=True)

        # Also heal patient_medications document
        db.collection('patient_medications').document(elder_id).set({
            'caregiverId': caregiver_id
        }, merge=True)
        
        return jsonify({"message": "Permissions fixed successfully"}), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@meds_bp.route('/save', methods=['POST'])
def save_medications():
    data = request.get_json()
    elder_id = data.get("elder_id")
    meds = data.get("medications", [])

    if not elder_id:
        return jsonify({"error": "elder_id required"}), 400
    
    if not meds:
        # Allow empty save (user might have deleted all)
        pass

    # Validate
    try:
        meds_valid = [Medication(**m).model_dump() for m in meds]
    except Exception as e:
        print(f"Validation Error: {e}")
        print(f"Received Data: {meds}")
        return jsonify({"error": f"Validation error: {e}"}), 400

    # 1. Fetch Profile for Denormalization (Name, Age)
    elder_name = "Unknown"
    elder_age = 65
    caregiver_id = None
    try:
        profile_ref = db.collection("elder_profiles").document(elder_id)
        profile_doc = profile_ref.get()
        if profile_doc.exists:
            p_data = profile_doc.to_dict()
            elder_name = p_data.get("name") or p_data.get("full_name") or "Nilu"
            raw_age = p_data.get("age")
            try:
                elder_age = int(raw_age) if raw_age is not None else 65
            except:
                elder_age = 65
        
        # 1.5 Fetch caregiver_id from elders collection
        elder_main_doc = db.collection("elders").document(elder_id).get()
        if elder_main_doc.exists:
            caregiver_id = elder_main_doc.to_dict().get("caregiverId")
            
    except Exception as e:
        print(f"Warning: Could not fetch profile or caregiver for denormalization: {e}")

    # 2. Existing Storage (Hierarchical - Prescription Packet)
    doc = {
        "elder_id": elder_id,
        "medications": meds_valid,
        "created_at": datetime.utcnow().isoformat()
    }
    db.collection("elders").document(elder_id).collection("prescriptions").add(doc)

    # 3. New Single-Document Storage (patient_medications)
    now = datetime.now()
    current_date_str = now.strftime("%Y-%m-%d")
    
    # Helper to parse duration and calculate end date
    def calculate_end_date(start_date_str, duration_str):
        if not duration_str:
            return "Ongoing"
        
        try:
            # Case-insensitive search for numbers and units
            duration_str = duration_str.lower()
            match = re.search(r'(\d+)\s*(day|week|month|year)', duration_str)
            if not match:
                return "Ongoing"
            
            value = int(match.group(1))
            unit = match.group(2)
            
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
            
            if 'day' in unit:
                end_date = start_date + timedelta(days=value)
            elif 'week' in unit:
                end_date = start_date + timedelta(weeks=value)
            elif 'month' in unit:
                # Approximate 30 days per month
                end_date = start_date + timedelta(days=value * 30)
            elif 'year' in unit:
                end_date = start_date + timedelta(days=value * 365)
            else:
                return "Ongoing"
            
            return end_date.strftime("%Y-%m-%d")
        except Exception as e:
            print(f"Error calculating end date: {e}")
            return "Ongoing"

    # Prepare list of flat medication docs to append
    new_meds_to_add = []
    for m in meds_valid:
        duration = m.get("duration")
        end_date = calculate_end_date(current_date_str, duration)
        
        flat_doc = {
            "drug_name": m.get("drug_name"),
            "dosage": m.get("dosage"),
            "timing": m.get("timing"),
            "frequency": m.get("frequency"),
            "status": "active",
            "start_date": current_date_str,
            "end_date": end_date,
            "notes": m.get("notes"),
            "confidence": m.get("confidence", 0.0),
            "created_at": datetime.utcnow().isoformat()
        }
        new_meds_to_add.append(flat_doc)

    # Update or create the single document for this elder
    try:
        med_doc_ref = db.collection("patient_medications").document(elder_id)
        
        # We use arrayUnion to append new medications to the list
        med_doc_ref.set({
            "elder_id": elder_id,
            "elder_name": elder_name,
            "elder_age": elder_age,
            "caregiverId": caregiver_id,
            "medications": firestore.ArrayUnion(new_meds_to_add),
            "last_updated": datetime.utcnow().isoformat()
        }, merge=True)
    except Exception as e:
        print(f"Error updating flat storage: {e}")
        # Continue anyway as hierarchical storage succeeded

    return jsonify({"ok": True}), 200

@meds_bp.route('/assign_therapy', methods=['POST'])
def assign_therapy():
    try:
        data = request.json
        # Expects: { 'elder_uid': '...', 'activity_name': '...', 'duration': '10 mins', 'instructions': '...' }
        db.collection('therapy_assignments').add(data)
        return jsonify({"message": "Therapy assigned successfully"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@meds_bp.route('/add_medication', methods=['POST'])
def add_medication():
    try:
        data = request.json
        elder_id = data.get('elder_id') or data.get('elder_uid')
        
        if not elder_id:
            return jsonify({"error": "elder_id required"}), 400

        # Fetch basic info for denormalization
        elder_name = "Nilu"
        elder_age = 65
        caregiver_id = None
        try:
            profile_doc = db.collection("elder_profiles").document(elder_id).get()
            if profile_doc.exists:
                p_data = profile_doc.to_dict()
                elder_name = p_data.get("name") or p_data.get("full_name") or "Nilu"
                elder_age = int(p_data.get("age") or 65)

            elder_main_doc = db.collection("elders").document(elder_id).get()
            if elder_main_doc.exists:
                caregiver_id = elder_main_doc.to_dict().get("caregiverId")
        except:
            pass

        now_str = datetime.now().strftime("%Y-%m-%d")
        
        # Format for patient_medications array
        new_med = {
            "drug_name": data.get("drug_name"),
            "dosage": data.get("dosage"),
            "timing": data.get("timing", "unknown"),
            "frequency": data.get("frequency"),
            "status": "active",
            "start_date": now_str,
            "end_date": "Ongoing",
            "notes": data.get("notes"),
            "confidence": 1.0, # Manual entry is 100% confident
            "created_at": datetime.utcnow().isoformat()
        }

        # Save to single document storage
        med_doc_ref = db.collection("patient_medications").document(elder_id)
        med_doc_ref.set({
            "elder_id": elder_id,
            "elder_name": elder_name,
            "elder_age": elder_age,
            "caregiverId": caregiver_id,
            "medications": firestore.ArrayUnion([new_med]),
            "last_updated": datetime.utcnow().isoformat()
        }, merge=True)

        # Legacy fallback (Optional)
        db.collection('medication_prescriptions').add({
            **data,
            "is_active": True,
            "created_at": datetime.utcnow().isoformat()
        })

        return jsonify({"message": "Medication added successfully", "medication": new_med}), 201
    except Exception as e:
        print(f"Error in add_medication: {e}")
        return jsonify({"error": str(e)}), 500
