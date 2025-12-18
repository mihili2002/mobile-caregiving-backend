# """Patient-related API routes."""
# from fastapi import APIRouter, Depends
# from app.api.deps import get_current_user

# router = APIRouter(prefix="/patients", tags=["patients"])


# @router.get("/")
# async def list_patients(user=Depends(get_current_user)):
#     return {"items": []}
    
"""Patient-related API routes."""

from fastapi import APIRouter, Depends, Body
from app.api.deps import get_current_user
from app.core import firebase

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("/")
async def list_patients(user=Depends(get_current_user)):
    docs = (
        firebase.db
        .collection("patients")
        .where("created_by", "==", user["uid"])
        .stream()
    )

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
