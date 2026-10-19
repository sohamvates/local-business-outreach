from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Email, Company
from services.do_not_contact_service import mark_company_do_not_contact, serialize_dnc_entry, get_company_dnc_match
from services.signature_service import ensure_signature, identity_for_company_type, refresh_signatures

router = APIRouter(prefix="/api/review", tags=["review_queue"])


class EditPayload(BaseModel):
    subject: str = ""
    body: str = ""


class DoNotContactPayload(BaseModel):
    reason: str = "unsubscribed"
    notes: str = ""


@router.get("")
def list_pending(db: Session = Depends(get_db)):
    # Bring stale signatures up to date before listing, so the queue never shows
    # a block the user has to correct by hand. Idempotent — see refresh_signatures.
    refresh_signatures(db)
    emails = db.query(Email).filter(Email.status == "pending").order_by(Email.created_at.desc()).all()
    return [_serialize(e, db) for e in emails]


@router.get("/all")
def list_all(db: Session = Depends(get_db)):
    refresh_signatures(db)
    emails = db.query(Email).order_by(Email.created_at.desc()).all()
    return [_serialize(e, db) for e in emails]


@router.patch("/{email_id}/approve")
def approve_email(email_id: int, db: Session = Depends(get_db)):
    email = db.get(Email, email_id)
    if not email:
        return {"ok": False, "message": "Email not found."}
    if email.company:
        email.body = ensure_signature(email.body, email.company.company_type)
        email.from_address = identity_for_company_type(email.company.company_type)["from_email"]
    email.status = "approved"
    email.reviewed_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.patch("/{email_id}/discard")
def discard_email(email_id: int, db: Session = Depends(get_db)):
    email = db.get(Email, email_id)
    if not email:
        return {"ok": False, "message": "Email not found."}
    email.status = "discarded"
    email.reviewed_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.patch("/{email_id}/edit")
def edit_email(email_id: int, payload: EditPayload, db: Session = Depends(get_db)):
    email = db.get(Email, email_id)
    if not email:
        return {"ok": False, "message": "Email not found."}
    if payload.subject:
        email.subject = payload.subject
    if payload.body:
        company_type = email.company.company_type if email.company else None
        email.body = ensure_signature(payload.body, company_type)
        email.from_address = identity_for_company_type(company_type)["from_email"]
    db.commit()
    return {"ok": True, "subject": email.subject, "body": email.body, "from_address": email.from_address}


@router.post("/{email_id}/do-not-contact")
def mark_review_email_do_not_contact(
    email_id: int,
    payload: DoNotContactPayload,
    db: Session = Depends(get_db),
):
    email = db.get(Email, email_id)
    if not email or not email.company:
        return {"ok": False, "message": "Email or company not found."}
    entry = mark_company_do_not_contact(
        db,
        company=email.company,
        email=email,
        reason=payload.reason,
        source="review_queue",
        notes=payload.notes or "Marked from Review Queue.",
    )
    return {"ok": True, "message": "Marked as do not contact.", "entry": serialize_dnc_entry(entry)}


def _serialize(e: Email, db: Session) -> dict:
    company = db.get(Company, e.company_id) if e.company_id else None
    dnc_entry = get_company_dnc_match(db, company) if company else None
    return {
        "id": e.id,
        "company_id": e.company_id,
        "company_name": company.name if company else "Unknown",
        "company_type": company.company_type if company else None,
        "company_website": company.website if company else None,
        "company_email": company.email if company else None,
        "subject": e.subject,
        "body": e.body,
        "from_address": e.from_address,
        "status": e.status,
        "review_notes": e.review_notes,   # deliverability warnings from AI sanitizer
        "do_not_contact": serialize_dnc_entry(dnc_entry),
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }
