from fastapi import APIRouter, Depends, Body, HTTPException
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from app.api.deps import require_role
from app.core.firebase import get_db

router = APIRouter(prefix="/api/meal-plans", tags=["meal_plans"])


def _now_utc():
    return datetime.now(timezone.utc)


def _validate_meal_item(item: Dict[str, Any]):
    if not isinstance(item, dict):
        raise HTTPException(status_code=400, detail="Invalid meal item format")
    if not item.get("food_name") or not isinstance(item.get("food_name"), str):
        raise HTTPException(status_code=400, detail="Meal item missing food_name")
    if not item.get("portion") or not isinstance(item.get("portion"), str):
        raise HTTPException(status_code=400, detail="Meal item missing portion")
    # notes optional
    return True


def _validate_days(days: Any):
    if not isinstance(days, list):
        raise HTTPException(status_code=400, detail="days must be a list")
    for d in days:
        if not isinstance(d, dict):
            raise HTTPException(status_code=400, detail="each day must be an object")
        if "day" not in d:
            raise HTTPException(status_code=400, detail="each day must include 'day'")
        meals = d.get("meals")
        if meals is None or not isinstance(meals, dict):
            raise HTTPException(status_code=400, detail="each day must include 'meals' object")
        for meal_name in ("breakfast", "lunch", "dinner", "snacks"):
            items = meals.get(meal_name, [])
            if not isinstance(items, list):
                raise HTTPException(status_code=400, detail=f"{meal_name} must be a list")
            for it in items:
                _validate_meal_item(it)
    return True


@router.put("/{plan_id}")
async def replace_meal_plan(
    plan_id: str,
    payload: Dict[str, Any] = Body(...),
    user=Depends(require_role(["doctor", "admin"]))
):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Firestore client not initialized")

    ref = db.collection("meal_plans").document(plan_id)
    doc = ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Meal plan not found")

    # Validate days structure if provided
    incoming_days = payload.get("days")
    if incoming_days is None:
        raise HTTPException(status_code=400, detail="Missing 'days' in payload")
    _validate_days(incoming_days)

    # Prevent changing the document id
    payload_id = payload.get("id")
    if payload_id and payload_id != plan_id:
        raise HTTPException(status_code=400, detail="plan id mismatch")

    # Prepare replacement doc: keep some existing fields if not provided
    current = doc.to_dict() or {}

    new_doc = payload.copy()
    # Ensure planId consistency: do not write an 'id' field into Firestore
    new_doc.pop("id", None)

    # Keep created_at if present in current and not provided
    if "created_at" in current and "created_at" not in new_doc:
        new_doc["created_at"] = current.get("created_at")

    new_doc["updated_at"] = _now_utc()
    new_doc["updated_by"] = user["uid"]

    try:
        # Full replace of document contents (excluding the Firestore id)
        ref.set(new_doc)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database update failed: {e}")

    out = {"id": plan_id, **new_doc}
    return {"success": True, "data": out}


@router.patch("/{plan_id}/days")
async def patch_meal_plan_days(
    plan_id: str,
    body: Dict[str, Any] = Body(...),
    user=Depends(require_role(["doctor", "admin"]))
):
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Firestore client not initialized")

    ref = db.collection("meal_plans").document(plan_id)
    doc = ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Meal plan not found")

    days = body.get("days")
    if days is None:
        raise HTTPException(status_code=400, detail="Missing 'days' in payload")
    _validate_days(days)

    mode = body.get("mode", "replace")  # replace or merge

    current = doc.to_dict() or {}
    current_days = current.get("days", [])

    if mode == "replace":
        new_days = days
    else:
        # merge: replace by matching 'day' field, append new days if not found
        new_days = list(current_days)
        # build index by day value (day may be int or string)
        idx = {}
        for i, d in enumerate(new_days):
            idx_key = d.get("day")
            idx[idx_key] = i

        for incoming in days:
            key = incoming.get("day")
            if key in idx:
                new_days[idx[key]] = incoming
            else:
                new_days.append(incoming)

    updates = {
        "days": new_days,
        "updated_at": _now_utc(),
        "updated_by": user["uid"],
    }

    try:
        ref.update(updates)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database update failed: {e}")

    out = {"id": plan_id, **(current or {})}
    out.update(updates)

    return {"success": True, "data": out}
