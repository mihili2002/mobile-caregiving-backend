from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
from typing import List, Optional, Any
from firebase_admin import firestore
from datetime import datetime, timedelta
import re

# router = APIRouter()
router = APIRouter(prefix="/api/medications", tags=["medications"])

# ----------------------------------------------------------------
# Pydantic Models for Validation
# ----------------------------------------------------------------

class FixPermissionsRequest(BaseModel):
    elder_id: str
    caregiver_id: str

class MedicationItem(BaseModel):
    drug_name: str
    dosage: str
    timing: Optional[str] = "unknown"
    frequency: Optional[str] = ""
    duration: Optional[str] = None
    notes: Optional[str] = None
    confidence: Optional[float] = 0.0
    # Allow extra fields if necessary
    
class SaveMedicationsRequest(BaseModel):
    elder_id: str
    medications: List[MedicationItem]

class AssignTherapyRequest(BaseModel):
    elder_uid: str
    activity_name: str
    duration: str
    instructions: Optional[str] = ""

class AddMedicationRequest(BaseModel):
    elder_id: Optional[str] = None
    elder_uid: Optional[str] = None # Support both keys
    drug_name: str
    dosage: str
    timing: Optional[str] = "unknown"
    frequency: Optional[str] = None
    notes: Optional[str] = None

# ----------------------------------------------------------------
# Helper Functions
# ----------------------------------------------------------------

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

# ----------------------------------------------------------------
# Routes
# ----------------------------------------------------------------

@router.post('/fix_permissions')
async def fix_permissions(req: FixPermissionsRequest):
    try:
        db = firestore.client()
        print(f"DEBUG: Entered fix_permissions endpoint with data: {req}")
        
        # Use Admin SDK to bypass rules
        doc_ref = db.collection('elders').document(req.elder_id)
        
        doc_ref.set({
            'caregiverId': req.caregiver_id
        }, merge=True)

        # Also heal patient_medications document
        db.collection('patient_medications').document(req.elder_id).set({
            'caregiverId': req.caregiver_id
        }, merge=True)
        
        return {"message": "Permissions fixed successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post('/save')
async def save_medications(req: SaveMedicationsRequest):
    try:
        db = firestore.client()
        elder_id = req.elder_id
        meds = req.medications

        # 1. Fetch Profile for Denormalization (Name, Age)
        elder_name = "Unknown"
        elder_age = 65
        caregiver_id = None
        
        try:
            # Try elder_profiles first
            profile_ref = db.collection("elder_profiles").document(elder_id)
            profile_doc = profile_ref.get()
            if profile_doc.exists:
                p_data = profile_doc.to_dict()
                elder_name = p_data.get("name") or p_data.get("full_name") or "Unknown"
                raw_age = p_data.get("age")
                try:
                    elder_age = int(raw_age) if raw_age is not None else 65
                except:
                    elder_age = 65
            
            # If name is still Unknown, try 'users' collection
            if elder_name == "Unknown":
                user_doc = db.collection("users").document(elder_id).get()
                if user_doc.exists:
                    elder_name = user_doc.to_dict().get("name", "Unknown")

            # 1.5 Fetch caregiver_id from elders collection
            elder_main_doc = db.collection("elders").document(elder_id).get()
            if elder_main_doc.exists:
                caregiver_id = elder_main_doc.to_dict().get("caregiverId")
                
        except Exception as e:
            print(f"Warning: Could not fetch profile or caregiver for denormalization: {e}")

        # 2. Existing Storage (Hierarchical - Prescription Packet)
        # Convert Pydantic models to dicts
        meds_dicts = [m.model_dump() for m in meds]
        
        doc = {
            "elder_id": elder_id,
            "medications": meds_dicts,
            "created_at": datetime.utcnow().isoformat()
        }
        db.collection("elders").document(elder_id).collection("prescriptions").add(doc)

        # 3. New Single-Document Storage (patient_medications)
        now = datetime.now()
        current_date_str = now.strftime("%Y-%m-%d")
        
        # Prepare list of flat medication docs to append
        new_meds_to_add = []
        for m in meds: # iterating over Pydantic models directly
            duration = m.duration
            end_date = calculate_end_date(current_date_str, duration)
            
            flat_doc = {
                "drug_name": m.drug_name,
                "dosage": m.dosage,
                "timing": m.timing,
                "frequency": m.frequency,
                "status": "active",
                "start_date": current_date_str,
                "end_date": end_date,
                "notes": m.notes,
                "confidence": m.confidence,
                "created_at": datetime.utcnow().isoformat()
            }
            new_meds_to_add.append(flat_doc)

        # Update or create the single document for this elder
        try:
            med_doc_ref = db.collection("patient_medications").document(elder_id)
            
            # We use arrayUnion to append new medications to the list
            # Ensuring elder_name and elder_id are saved as requested
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

        return {"ok": True}

    except HTTPException:
        raise
    except Exception as e:
        print(f"Save Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post('/assign_therapy')
async def assign_therapy(req: AssignTherapyRequest):
    try:
        db = firestore.client()
        data = req.model_dump()
        # Remap elder_uid to match whatever schema is expected if differnet, 
        # but generic adding to collection is fine.
        
        db.collection('therapy_assignments').add(data)
        return {"message": "Therapy assigned successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post('/add_medication')
async def add_medication(req: AddMedicationRequest):
    try:
        db = firestore.client()
        elder_id = req.elder_id or req.elder_uid
        
        if not elder_id:
            raise HTTPException(status_code=400, detail="elder_id required")

        # Fetch basic info for denormalization
        elder_name = "Unknown"
        elder_age = 65
        caregiver_id = None
        try:
            profile_doc = db.collection("elder_profiles").document(elder_id).get()
            if profile_doc.exists:
                p_data = profile_doc.to_dict()
                elder_name = p_data.get("name") or p_data.get("full_name") or "Unknown"
                elder_age = int(p_data.get("age") or 65)

            # Fallback to users collection if name is unknown
            if elder_name == "Unknown":
                user_doc = db.collection("users").document(elder_id).get()
                if user_doc.exists:
                    elder_name = user_doc.to_dict().get("name", "Unknown")

            elder_main_doc = db.collection("elders").document(elder_id).get()
            if elder_main_doc.exists:
                caregiver_id = elder_main_doc.to_dict().get("caregiverId")
        except:
            pass

        now_str = datetime.now().strftime("%Y-%m-%d")
        
        # Format for patient_medications array
        new_med = {
            "drug_name": req.drug_name,
            "dosage": req.dosage,
            "timing": req.timing,
            "frequency": req.frequency,
            "status": "active",
            "start_date": now_str,
            "end_date": "Ongoing",
            "notes": req.notes,
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

        # Legacy fallback (Optional - matching old logic)
        db.collection('medication_prescriptions').add({
            **req.model_dump(),
            "is_active": True,
            "created_at": datetime.utcnow().isoformat()
        })

        return {"message": "Medication added successfully", "medication": new_med}
    except Exception as e:
        print(f"Error in add_medication: {e}")
        raise HTTPException(status_code=500, detail=str(e))
