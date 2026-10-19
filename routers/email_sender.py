from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Email, Company
from services.email_service import (
    RESUME_PATH,
    build_sample_message,
    daily_quota_state,
    deliverability_safe_mode_enabled,
    resume_exists,
    send_batch as _send_batch,
    send_email as _send,
    send_test_email as _send_test_email,
)

router = APIRouter(prefix="/api/send", tags=["email_sender"])


class SendPayload(BaseModel):
    via: str = "auto"          # "gmail" | "custom" | "auto" (routes by company_type)
    attach_resume: bool = False


class BatchPayload(BaseModel):
    email_ids: list[int]
    via: str = "auto"
    attach_resume: bool = False


class TestEmailPayload(BaseModel):
    recipient_email: str
    via: str = "gmail"
    subject: str = "Test email"
    body: str = "This is a test email from Nearletter."
    attach_resume: bool = False


# IMPORTANT: /batch must be declared BEFORE /{email_id} — FastAPI matches in
# declaration order; otherwise "batch" is parsed as an integer and fails with 422.

@router.post("/batch")
async def send_batch(payload: BatchPayload, db: Session = Depends(get_db)):
    return await _send_batch(payload.email_ids, payload.via, db, attach_resume=payload.attach_resume)


@router.get("/approved")
def list_approved(db: Session = Depends(get_db)):
    emails = (
        db.query(Email)
        .filter(Email.status == "approved")
        .order_by(Email.created_at.desc())
        .all()
    )
    return [_serialize(e, db) for e in emails]


@router.get("/status")
def get_sender_status(db: Session = Depends(get_db)):
    return {
        "ok": True,
        "deliverability_safe_mode": deliverability_safe_mode_enabled(),
        "daily_quota": daily_quota_state(db),
    }


@router.get("/resume")
def get_resume_status():
    path = Path(RESUME_PATH)
    exists = path.exists()
    return {
        "ok": True,
        "exists": exists,
        "filename": path.name,
        "path": "static/assets/resume.pdf",
        "size_bytes": path.stat().st_size if exists else 0,
    }


@router.post("/resume")
async def upload_resume(file: UploadFile = File(...)):
    filename = (file.filename or "").strip()
    content_type = (file.content_type or "").lower()
    if not filename.lower().endswith(".pdf") and content_type != "application/pdf":
        return {"ok": False, "message": "Resume upload must be a PDF file."}

    content = await file.read()
    if not content.startswith(b"%PDF"):
        return {"ok": False, "message": "Uploaded file is not a valid PDF."}

    path = Path(RESUME_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {"ok": True, "message": f"Resume uploaded as {path.name}.", "size_bytes": len(content)}


@router.post("/test-email")
async def send_test_email(payload: TestEmailPayload):
    return await _send_test_email(
        payload.recipient_email,
        payload.via,
        payload.subject,
        payload.body,
        attach_resume=payload.attach_resume,
    )


@router.post("/{email_id}")
async def send_single(email_id: int, payload: SendPayload, db: Session = Depends(get_db)):
    return await _send(email_id, payload.via, db, attach_resume=payload.attach_resume)


@router.get("/sample")
def get_sample_email():
    """
    Build and return a fully-rendered sample email (fictional agency)
    so the user can verify headers, plain text, and HTML output before sending.
    """
    msg = build_sample_message()

    # Extract each MIME part
    plain_text = html_body = None
    for part in msg.walk():
        ct = part.get_content_type()
        charset = part.get_content_charset() or "utf-8"
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        decoded = payload.decode(charset)
        if ct == "text/plain" and plain_text is None:
            plain_text = decoded
        elif ct == "text/html" and html_body is None:
            html_body = decoded

    # Collect headers in insertion order
    headers = {k: msg[k] for k in msg.keys()}

    return {
        "headers": headers,
        "plain_text": plain_text,
        "html": html_body,
        # These notes describe what _build_mime actually produces. If the MIME
        # builder changes, update this list in the same commit — a preview that
        # overstates the real output gives false confidence before a send.
        "deliverability_notes": [
            "✓ From includes display name (reduces spam score)",
            "✓ Reply-To matches From (no mismatch)",
            "✓ Envelope sender matches the From header (SPF/DMARC alignment)",
            "✓ Message-ID scoped to sending domain",
            "✓ Date in RFC 2822 UTC format",
            "✓ Plain text only — no HTML, no external images, no tracking pixels",
            "✓ No clickable links in client emails (stripped before send)",
            "✓ List-Unsubscribe header (mailto) plus plain text opt-out line",
            "✓ Batch sends use 3–5 s random delay between messages",
            "⚠ SPF, DKIM and DMARC are NOT verified by this system — check the "
            "DNS records yourself and confirm with Test Email → Gmail → Show original",
        ],
    }


def _serialize(e: Email, db: Session) -> dict:
    company = db.get(Company, e.company_id) if e.company_id else None
    return {
        "id": e.id,
        "company_id": e.company_id,
        "company_name": company.name if company else "Unknown",
        "company_type": company.company_type if company else None,
        "company_email": company.email if company else None,
        "subject": e.subject,
        "body": e.body,
        "from_address": e.from_address,
        "status": e.status,
        "review_notes": e.review_notes,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }
