"""
CRM service — Google Sheets sync and follow-up management.

Google Sheets auth: uses a service account JSON key at google-service-account.json
in the project root. The service account must be granted Editor access to the sheet.

Setup steps (one-time):
  1. Google Cloud Console → IAM → Service Accounts → Create
  2. Download JSON key → save as google-service-account.json in project root
  3. Open your Google Sheet → Share → paste the service account email (ends in @...iam.gserviceaccount.com)
"""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from models import OutreachRecord, Company, Email

SA_KEY_PATH = Path(__file__).parent.parent / "google-service-account.json"

SHEET_HEADERS = [
    "Record ID", "Company", "Website", "Email",
    "Status", "Sent Date", "Follow-up Date", "Replied Date",
    "Follow-up Sent", "Notes",
]

FOLLOW_UP_DAYS = 5


def _get_sheets_service():
    """Return an authenticated Google Sheets API client or raise."""
    if not SA_KEY_PATH.exists():
        raise FileNotFoundError(
            "google-service-account.json not found. "
            "Download a service account key from Google Cloud Console and save it to the project root."
        )
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        str(SA_KEY_PATH),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return build("sheets", "v4", credentials=creds)


def _get_sheet_id() -> str:
    import re
    from services.settings_service import get_raw
    raw = get_raw("GOOGLE_SHEETS_ID")
    if not raw:
        raise ValueError("GOOGLE_SHEETS_ID is not configured in Settings.")
    # Accept either a bare ID or a full Sheets URL
    # e.g. https://docs.google.com/spreadsheets/d/<ID>/edit?...
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", raw)
    if m:
        return m.group(1)
    # Already a bare ID (no slashes)
    return raw.strip()


def _record_to_row(r: OutreachRecord, company: Company | None, email: Email | None) -> list:
    return [
        r.id,
        company.name if company else "",
        company.website if company else "",
        company.email if company else "",
        r.status,
        r.sent_at.strftime("%Y-%m-%d %H:%M") if r.sent_at else "",
        r.follow_up_date.strftime("%Y-%m-%d") if r.follow_up_date else "",
        r.replied_at.strftime("%Y-%m-%d %H:%M") if r.replied_at else "",
        "Yes" if r.follow_up_sent else "No",
        r.notes or "",
    ]


def sync_to_sheets(db: Session) -> dict:
    """
    Full sync: write all OutreachRecords to the Google Sheet.
    Clears the sheet first, then rewrites header + all rows.
    Returns setup_required=True if google-service-account.json is missing.
    """
    try:
        service = _get_sheets_service()
        sheet_id = _get_sheet_id()
    except FileNotFoundError as e:
        return {
            "ok": False,
            "setup_required": True,
            "message": str(e),
        }
    except ValueError as e:
        return {"ok": False, "setup_required": False, "message": str(e)}
    except Exception as e:
        return {"ok": False, "setup_required": False, "message": f"Google auth error: {e}"}

    records = db.query(OutreachRecord).order_by(OutreachRecord.created_at).all()
    rows = [SHEET_HEADERS]
    for r in records:
        company = db.get(Company, r.company_id)
        email = db.get(Email, r.email_id) if r.email_id else None
        rows.append(_record_to_row(r, company, email))

    sheet_range = "Sheet1!A1"
    try:
        # Clear existing content
        service.spreadsheets().values().clear(
            spreadsheetId=sheet_id,
            range="Sheet1",
        ).execute()

        # Write all rows
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=sheet_range,
            valueInputOption="RAW",
            body={"values": rows},
        ).execute()

        return {"ok": True, "message": f"Synced {len(records)} records to Google Sheets."}
    except Exception as e:
        return {"ok": False, "message": f"Sheets API error: {e}"}


def export_csv(db: Session) -> str:
    """Return all OutreachRecords as a CSV string."""
    import csv
    import io
    records = db.query(OutreachRecord).order_by(OutreachRecord.created_at).all()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(SHEET_HEADERS)
    for r in records:
        company = db.get(Company, r.company_id)
        email = db.get(Email, r.email_id) if r.email_id else None
        writer.writerow(_record_to_row(r, company, email))
    return out.getvalue()


def get_due_followups(db: Session) -> list[dict]:
    """Return OutreachRecords where follow-up is due and not yet sent."""
    now = datetime.utcnow()
    due = (
        db.query(OutreachRecord)
        .filter(
            OutreachRecord.follow_up_date <= now,
            OutreachRecord.follow_up_sent == False,  # noqa: E712
            OutreachRecord.status == "sent",
        )
        .all()
    )
    result = []
    for r in due:
        company = db.get(Company, r.company_id)
        result.append({
            "id": r.id,
            "company_name": company.name if company else "Unknown",
            "company_email": company.email if company else None,
            "sent_at": r.sent_at.isoformat() if r.sent_at else None,
            "follow_up_date": r.follow_up_date.isoformat() if r.follow_up_date else None,
            "days_since_sent": (now - r.sent_at).days if r.sent_at else None,
        })
    return result


async def send_followup(record_id: int, via: str, db: Session) -> dict:
    """Send a follow-up email for a given OutreachRecord."""
    from services.email_service import send_email as _send

    record = db.get(OutreachRecord, record_id)
    if not record:
        return {"ok": False, "message": "Record not found."}

    original_email = db.get(Email, record.email_id) if record.email_id else None
    if not original_email:
        return {"ok": False, "message": "Original email not found."}

    company = db.get(Company, record.company_id)
    if not company or not company.email:
        return {"ok": False, "message": "No recipient email address on file."}

    # Build follow-up email (references original)
    from models import Email as EmailModel
    followup = EmailModel(
        company_id=company.id,
        subject=f"Re: {original_email.subject}",
        body=(
            f"Hi,\n\n"
            f"I wanted to follow up on my previous email regarding {company.name}.\n\n"
            f"I know things get busy — I just wanted to make sure this didn't get buried. "
            f"I'd love to find 15 minutes to chat about how we might be able to help.\n\n"
            f"Happy to work around your schedule.\n\n"
            f"Best,\n{original_email.from_address}"
        ),
        from_address=original_email.from_address,
        status="approved",
    )
    db.add(followup)
    db.flush()

    result = await _send(followup.id, via, db)
    if result["ok"]:
        record.follow_up_sent = True
        record.status = "follow_up"
        db.commit()

    return result
