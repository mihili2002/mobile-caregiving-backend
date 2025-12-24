# """Patient-related API routes."""
# from fastapi import APIRouter, Depends
# from app.api.deps import get_current_user

# router = APIRouter(prefix="/patients", tags=["patients"])


# @router.get("/")
# async def list_patients(user=Depends(get_current_user)):
#     return {"items": []}
    
"""Patient-related API routes."""

from fastapi import APIRouter, Depends, Body, HTTPException
from app.api.deps import get_current_user, require_role
from app.core import firebase

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("/")
async def list_patients(user=Depends(get_current_user)):
    """List patients.

    - If caller is a doctor/caregiver they can list all patients.
    - Otherwise only return patients created by the caller.
    """
    role = user.get("role") or user.get("roles")
    coll = firebase.db.collection("patients")

    if role == "doctor" or (isinstance(role, list) and "doctor" in role):
        docs = coll.stream()
    else:
        docs = coll.where("created_by", "==", user["uid"]).stream()

    return {
        "items": [
            {"id": doc.id, **doc.to_dict()}
            for doc in docs
        ]
    }


@router.post("/")
async def create_patient(
    data: dict = Body(...),
    user=Depends(get_current_user)
):
    doc_ref = firebase.db.collection("patients").add({
        **data,
        "created_by": user["uid"]
    })

    return {
        "message": "Patient created successfully",
        "id": doc_ref[1].id
    }


# TEMPORARY DEV ENDPOINT (NO AUTH)
@router.post("/_dev_test_create")
async def dev_test_create_patient():
    doc_ref = firebase.db.collection("patients").add({
        "name": "Dev Test Patient",
        "age": 65,
        "created_by": "dev_test_user"
    })

    return {
        "message": "Dev test patient created",
        "id": doc_ref[1].id
    }
