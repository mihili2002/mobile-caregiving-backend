from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from firebase_admin import firestore
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from app.core.firebase import get_db
import os

router = APIRouter(prefix="/api/therapy", tags=["Therapy Plans"])

db = get_db()

# ====================================================
# 🧠 Intervention Repository (MUST MATCH: Low / Medium / High)
# ====================================================
INTERVENTION_LIBRARY = {
    "Depression_Risk": {
        "Low": [
            {"activity": "Daily sunlight walk", "duration": "20 mins"},
            {"activity": "Gratitude journaling", "duration": "10 mins"},
        ],
        "Medium": [
            {"activity": "Structured daily routine", "duration": "Full day plan"},
            {"activity": "Behavioral activation activity", "duration": "30 mins"},
            {"activity": "Weekly therapy session", "duration": "1 hour"},
        ],
        "High": [
            {"activity": "CBT-based structured therapy", "duration": "1 hour/session"},
            {"activity": "Close mood monitoring", "duration": "Daily"},
            {"activity": "Emergency support check-in", "duration": "Immediate"},
        ],
    },
    "Anxiety_Risk": {
        "Low": [{"activity": "4-7-8 breathing", "duration": "5 mins"}],
        "Medium": [
            {"activity": "Grounding exercise 5-4-3-2-1", "duration": "10 mins"},
            {"activity": "Progressive muscle relaxation", "duration": "10 mins"},
        ],
        "High": [
            {"activity": "Guided CBT for anxiety", "duration": "1 hour"},
            {"activity": "Daily relaxation training", "duration": "20 mins"},
        ],
    },
    "Insomnia_Risk": {
        "Low": [{"activity": "Sleep hygiene tips", "duration": "Daily habit"}],
        "Medium": [
            {"activity": "No screens 60 mins before bed", "duration": "Daily"},
            {"activity": "Consistent sleep schedule", "duration": "Daily"},
        ],
        "High": [
            {"activity": "CBT-I structured program", "duration": "6 weeks"},
            {"activity": "Sleep diary tracking", "duration": "Daily"},
        ],
    },
    "Emotional_WellBeing_Risk": {
        "Low": [{"activity": "Weekly social interaction goal", "duration": "Weekly"}],
        "Medium": [
            {"activity": "Daily mood tracking", "duration": "5 mins"},
            {"activity": "Hobby engagement", "duration": "20 mins"},
        ],
        "High": [
            {"activity": "Intensive emotional regulation training", "duration": "Weekly session"},
            {"activity": "Support group participation", "duration": "Weekly"},
        ],
    },
}

# ====================================================
# 🧠 Generate Personalized Plan
# ====================================================
@router.post("/generate_personalized_plan")
def generate_personalized_plan(payload: dict):

    resident_id = payload.get("resident_id")

    if not resident_id:
        raise HTTPException(status_code=400, detail="resident_id required")

    risk_docs = (
        db.collection("risk_assessments")
        .where("residentId", "==", resident_id)
        .order_by("createdAt", direction=firestore.Query.DESCENDING)
        .limit(1)
        .stream()
    )

    latest = None
    for doc in risk_docs:
        latest = doc.to_dict()

    if not latest:
        raise HTTPException(status_code=404, detail="No risk assessment found")

    domain_levels = {
        "Depression_Risk": latest.get("depLevel"),
        "Anxiety_Risk": latest.get("anxLevel"),
        "Insomnia_Risk": latest.get("insLevel"),
        "Emotional_WellBeing_Risk": latest.get("emoLevel"),
    }

    priority_order = {"High": 3, "Medium": 2, "Low": 1}

    sorted_domains = sorted(
        domain_levels.items(),
        key=lambda x: priority_order.get(x[1], 0),
        reverse=True,
    )

    generated_plan = []
    total_interventions = 0
    MAX_INTERVENTIONS = 8

    for domain, level in sorted_domains:

        if not level:
            continue

        interventions = INTERVENTION_LIBRARY.get(domain, {}).get(level)

        if not interventions:
            continue

        if total_interventions >= MAX_INTERVENTIONS:
            break

        generated_plan.append({
            "domain": domain,
            "severity": level,
            "interventions": interventions,
        })

        total_interventions += len(interventions)

    plan_ref = db.collection("personalized_plans").document()

    plan_data = {
        "id": plan_ref.id,
        "residentId": resident_id,
        "generatedAt": datetime.utcnow().isoformat(),
        "domains": generated_plan,
        "status": "Pending Therapist Approval",
        "source": "AI_Generated",
    }

    plan_ref.set(plan_data)

    return {"message": "Plan generated", "plan": plan_data}


# ====================================================
# ✅ Approve Plan (Save Edited Version)
# ====================================================
@router.post("/approve_plan")
def approve_plan(payload: dict):

    plan_id = payload.get("plan_id")
    therapist_name = payload.get("therapist_name", "Therapist")
    updated_domains = payload.get("domains")

    if not plan_id:
        raise HTTPException(status_code=400, detail="plan_id required")

    plan_ref = db.collection("personalized_plans").document(plan_id)
    doc = plan_ref.get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Plan not found")

    update_data = {
        "status": "Active",
        "approvedAt": datetime.utcnow().isoformat(),
        "approvedBy": therapist_name,
    }

    if updated_domains:
        update_data["domains"] = updated_domains
        update_data["source"] = "Therapist_Modified"

    plan_ref.update(update_data)

    return {"message": "Plan approved", "plan_id": plan_id}


# ====================================================
# 📄 Export Plan as PDF
# ====================================================
@router.get("/export_plan_pdf/{plan_id}")
def export_plan_pdf(plan_id: str):

    plan_ref = db.collection("personalized_plans").document(plan_id)
    doc = plan_ref.get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Plan not found")

    plan = doc.to_dict()

    file_path = f"/tmp/{plan_id}.pdf"

    pdf = SimpleDocTemplate(file_path, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph("Clinical Personalized Therapy Report", styles["Title"]))
    elements.append(Spacer(1, 0.3 * inch))
    elements.append(Paragraph(f"Resident ID: {plan['residentId']}", styles["Normal"]))
    elements.append(Paragraph(f"Status: {plan['status']}", styles["Normal"]))
    elements.append(Spacer(1, 0.3 * inch))

    for domain in plan["domains"]:

        elements.append(
            Paragraph(
                f"{domain['domain']} (Severity: {domain['severity']})",
                styles["Heading2"],
            )
        )
        elements.append(Spacer(1, 0.2 * inch))

        bullets = []

        for item in domain["interventions"]:
            text = f"{item['activity']} ({item.get('duration', '')})"
            bullets.append(ListItem(Paragraph(text, styles["Normal"])))

        elements.append(ListFlowable(bullets, bulletType="bullet"))
        elements.append(Spacer(1, 0.3 * inch))

    pdf.build(elements)

    return FileResponse(
        file_path,
        media_type="application/pdf",
        filename=f"therapy_plan_{plan_id}.pdf",
    )


# ====================================================
# Manual Recommendation
# ====================================================
@router.post("/save_recommendation")
def save_recommendation(payload: dict):

    elder_id = payload.get("elder_id")
    activity_name = payload.get("activity_name")

    if not elder_id or not activity_name:
        raise HTTPException(
            status_code=400,
            detail="elder_id and activity_name are required",
        )

    doc_ref = db.collection("therapy_assignments").document()

    assignment_data = {
        "id": doc_ref.id,
        "elder_id": elder_id,
        "activity_name": activity_name,
        "duration": payload.get("duration", "30 mins"),
        "instructions": payload.get("instructions", ""),
        "assigned_by": payload.get("assigned_by", "Therapist"),
        "date_assigned": datetime.utcnow().isoformat(),
        "is_active": True,
        "type": "therapist",
    }

    doc_ref.set(assignment_data)

    return {"message": "Recommendation saved", "id": doc_ref.id}