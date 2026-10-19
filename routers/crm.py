from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from database import get_db
from models import OutreachRecord, Company, Email
from services.crm_service import sync_to_sheets, export_csv, get_due_followups, send_followup
from services.do_not_contact_service import get_company_dnc_match, mark_company_do_not_contact, serialize_dnc_entry
from constants import VALID_OUTREACH_STATUSES, OutreachStatus

router = APIRouter(prefix="/api/crm", tags=["crm"])


class StatusUpdate(BaseModel):
    status: str
    notes: str = ""

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in VALID_OUTREACH_STATUSES:
            raise ValueError(
                f"Invalid status '{v}'. Must be one of: {', '.join(sorted(VALID_OUTREACH_STATUSES))}"
            )
        return v


class FollowUpPayload(BaseModel):
    via: str = "gmail"


class DoNotContactPayload(BaseModel):
    reason: str = "unsubscribed"
    notes: str = ""


@router.get("")
def list_records(db: Session = Depends(get_db)):
    records = (
        db.query(OutreachRecord)
        .order_by(OutreachRecord.created_at.desc())
        .all()
    )
    return [_serialize(r, db) for r in records]


@router.patch("/{record_id}/status")
def update_status(record_id: int, payload: StatusUpdate, db: Session = Depends(get_db)):
    record = db.get(OutreachRecord, record_id)
    if not record:
        return {"ok": False, "message": "Record not found."}
    from datetime import datetime
    record.status = payload.status
    if payload.notes:
        record.notes = payload.notes
    if payload.status == OutreachStatus.REPLIED.value and not record.replied_at:
        record.replied_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.post("/sync-sheets")
def sync_sheets(db: Session = Depends(get_db)):
    return sync_to_sheets(db)


@router.get("/export-csv")
def download_csv(db: Session = Depends(get_db)):
    csv_content = export_csv(db)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=outreach-crm.csv"},
    )


@router.get("/followups")
def list_due_followups(db: Session = Depends(get_db)):
    return get_due_followups(db)


@router.post("/followups/{record_id}/send")
async def send_followup_email(record_id: int, payload: FollowUpPayload, db: Session = Depends(get_db)):
    return await send_followup(record_id, payload.via, db)


@router.post("/{record_id}/do-not-contact")
def mark_record_do_not_contact(
    record_id: int,
    payload: DoNotContactPayload,
    db: Session = Depends(get_db),
):
    record = db.get(OutreachRecord, record_id)
    if not record:
        return {"ok": False, "message": "Record not found."}
    company = db.get(Company, record.company_id)
    if not company:
        return {"ok": False, "message": "Company not found."}
    email = db.get(Email, record.email_id) if record.email_id else None
    entry = mark_company_do_not_contact(
        db,
        company=company,
        outreach_record=record,
        email=email,
        reason=payload.reason,
        source="crm",
        notes=payload.notes or "Marked from CRM.",
    )
    return {"ok": True, "message": "Marked as do not contact.", "entry": serialize_dnc_entry(entry)}


def _serialize(r: OutreachRecord, db: Session) -> dict:
    company = db.get(Company, r.company_id)
    email = db.get(Email, r.email_id) if r.email_id else None
    dnc_entry = get_company_dnc_match(db, company) if company else None
    return {
        "id": r.id,
        "company_id": r.company_id,
        "company_name": company.name if company else "Unknown",
        "company_email": company.email if company else None,
        "company_website": company.website if company else None,
        "email_subject": email.subject if email else None,
        "sent_via": email.from_address if email else None,
        "status": r.status,
        "sent_at": r.sent_at.isoformat() if r.sent_at else None,
        "replied_at": r.replied_at.isoformat() if r.replied_at else None,
        "follow_up_date": r.follow_up_date.isoformat() if r.follow_up_date else None,
        "follow_up_sent": r.follow_up_sent,
        "notes": r.notes,
        "do_not_contact": serialize_dnc_entry(dnc_entry),
    }
