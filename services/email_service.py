"""
Email service — sends outreach emails via Gmail SMTP or custom SMTP.
Cold outreach is sent as plain text only. Agencies may still include a PDF
attachment, but the message body itself remains plain text.
"""
import asyncio
import logging
import os
import random
import ssl
from datetime import datetime, time, timedelta
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path

import aiosmtplib
from sqlalchemy.orm import Session

from models import Email, OutreachRecord
from services.dedup_service import company_has_contact_activity
from services.do_not_contact_service import get_company_dnc_match
from services.signature_service import ensure_signature, identity_for_company_type, is_client_type
from services.settings_service import get_raw

FOLLOW_UP_DAYS = 5
logger = logging.getLogger(__name__)
DELIVERABILITY_REVIEW_KEYWORDS = (
    "spam words",
    "deliverability terms",
    "all caps",
    "punctuation",
    "subject truncated",
    "subject warning",
)

_UNSUB_PLAIN = "\n\n---\nTo unsubscribe from these emails, reply with UNSUBSCRIBE."
# Absolute path resolution to avoid breaks when running from different directories
RESUME_PATH = str((Path(__file__).parent.parent / "static" / "assets" / "resume.pdf").resolve())


# ─── Config ───────────────────────────────────────────────────────────────────

def _resolve_via(via: str, company_type: str | None) -> str:
    """Resolve 'auto' to the correct SMTP account based on company type."""
    if via == "auto":
        from services.profile_service import forced_sending_via

        forced = forced_sending_via()
        if forced:
            return forced
        return "gmail" if company_type == "agency" else "custom"
    return via


def _smtp_config(via: str) -> dict:
    prefix = "GMAIL" if via == "gmail" else "CUSTOM"
    default_name = ""
    return {
        "hostname":     get_raw(f"{prefix}_SMTP_HOST"),
        "port":         int(get_raw(f"{prefix}_SMTP_PORT") or 587),
        "username":     get_raw(f"{prefix}_SMTP_USER"),
        "password":     get_raw(f"{prefix}_SMTP_PASSWORD"),
        "display_name": get_raw(f"{prefix}_FROM_NAME") or default_name,
    }


def resume_exists() -> bool:
    return os.path.exists(RESUME_PATH)


def deliverability_safe_mode_enabled() -> bool:
    return (get_raw("DELIVERABILITY_SAFE_MODE") or "true").strip().lower() == "true"


def daily_send_limit() -> int:
    """Max sends per calendar day. 0 disables the cap."""
    try:
        return max(0, int((get_raw("DAILY_SEND_LIMIT") or "25").strip()))
    except ValueError:
        return 25


def sends_today(db: Session) -> int:
    start = datetime.combine(datetime.utcnow().date(), time.min)
    return (
        db.query(OutreachRecord)
        .filter(OutreachRecord.sent_at >= start)
        .count()
    )


def daily_quota_state(db: Session) -> dict:
    limit = daily_send_limit()
    used = sends_today(db)
    return {
        "limit": limit,
        "used": used,
        "remaining": max(0, limit - used) if limit else None,
        "exhausted": bool(limit) and used >= limit,
    }


def email_has_deliverability_warnings(email: Email) -> bool:
    review_notes = (email.review_notes or "").strip().lower()
    return any(keyword in review_notes for keyword in DELIVERABILITY_REVIEW_KEYWORDS)


def deliverability_warning_message(email: Email) -> str | None:
    if not email_has_deliverability_warnings(email):
        return None
    return (email.review_notes or "Fix deliverability warnings before sending.").strip()


def _smtp_provider_response(send_result) -> str:
    if isinstance(send_result, tuple) and len(send_result) == 2:
        refused, response = send_result
        if refused:
            return f"refused={refused}; response={response}"
        return str(response)
    return str(send_result)


def _smtp_refusals(send_result) -> dict:
    if isinstance(send_result, tuple) and len(send_result) == 2 and isinstance(send_result[0], dict):
        return send_result[0]
    return {}


async def _send_smtp_message(
    msg: MIMEMultipart,
    *,
    cfg: dict,
    sender_type: str,
    from_addr: str,
    to_addr: str,
) -> dict:
    message_id = msg.get("Message-ID", "")
    log_context = (
        f"sender_type={sender_type} host={cfg['hostname']} port={cfg['port']} "
        f"start_tls=True auth=True from={from_addr} to={to_addr} message_id={message_id}"
    )
    logger.info("SMTP send attempt: %s", log_context)

    try:
        ctx = ssl.create_default_context()
        send_result = await aiosmtplib.send(
            msg,
            hostname=cfg["hostname"],
            port=cfg["port"],
            username=cfg["username"],
            password=cfg["password"],
            sender=from_addr,
            recipients=[to_addr],
            start_tls=True,
            tls_context=ctx,
        )
    except Exception as e:
        logger.warning("SMTP send failed: %s error=%s", log_context, e)
        return {"ok": False, "message": str(e), "message_id": message_id}

    provider_response = _smtp_provider_response(send_result)
    refusals = _smtp_refusals(send_result)
    logger.info("SMTP send response: %s provider_response=%s", log_context, provider_response)

    if refusals:
        return {
            "ok": False,
            "message": f"SMTP refused recipient(s): {refusals}",
            "message_id": message_id,
            "provider_response": provider_response,
        }

    return {
        "ok": True,
        "message_id": message_id,
        "provider_response": provider_response,
    }


# ─── MIME builder ─────────────────────────────────────────────────────────────

def _build_mime(
    display_name: str,
    from_addr: str,
    to_addr: str,
    subject: str,
    body: str,
    attach_resume: bool = False,
) -> MIMEMultipart:
    """
    Build a deliverability-hardened plain text MIME message.

    Structure without attachment:
      text/plain

    Structure with PDF attachment:
      multipart/mixed
        text/plain
        application/pdf
    """
    sending_domain = from_addr.split("@")[-1]
    from_field = formataddr((display_name, from_addr)) if display_name else from_addr

    plain = body.rstrip() + _UNSUB_PLAIN

    resume_bytes = None
    if attach_resume:
        with open(RESUME_PATH, "rb") as f:
            resume_bytes = f.read()

    if resume_bytes:
        outer = MIMEMultipart("mixed")
        outer.attach(MIMEText(plain, "plain", "utf-8"))
        pdf_part = MIMEApplication(resume_bytes, _subtype="pdf")
        pdf_part.add_header("Content-Disposition", 'attachment; filename="resume.pdf"')
        outer.attach(pdf_part)
        msg = outer
    else:
        msg = MIMEText(plain, "plain", "utf-8")

    msg["From"]       = from_field
    msg["To"]         = to_addr
    msg["Reply-To"]   = from_field
    msg["Subject"]    = subject
    msg["Message-ID"] = make_msgid(domain=sending_domain)
    msg["Date"]       = formatdate(usegmt=True)
    # Mailto-only unsubscribe: it matches the plain text instruction in the body
    # and gives filters a machine-readable opt-out path. List-Unsubscribe-Post is
    # deliberately absent — RFC 8058 one-click requires an HTTPS endpoint we do
    # not host, and advertising it without one is worse than omitting it.
    msg["List-Unsubscribe"] = f"<mailto:{from_addr}?subject=unsubscribe>"

    return msg


# ─── Send single ──────────────────────────────────────────────────────────────

async def send_email(
    email_id: int,
    via: str,
    db: Session,
    attach_resume: bool = False,
) -> dict:
    email = db.get(Email, email_id)
    if not email:
        return {"ok": False, "message": "Email not found."}
    if email.status != "approved":
        return {"ok": False, "message": f"Status is '{email.status}' — must be approved to send."}

    company = email.company
    to_addr = company.email if company else None
    if not to_addr:
        return {"ok": False, "message": f"'{company.name if company else '?'}' has no email address."}
    dnc_entry = get_company_dnc_match(db, company)
    if dnc_entry:
        return {
            "ok": False,
            "message": f"'{company.name}' is marked do not contact: {dnc_entry.reason}.",
        }
    if company and company_has_contact_activity(
        company,
        exclude_email_id=email.id,
        email_statuses={"sent"},
    ):
        return {"ok": False, "message": f"'{company.name}' already has outreach history. Duplicate send blocked."}

    # Resolve "auto" to the correct account based on the company type
    resolved_via = _resolve_via(via, company.company_type if company else None)
    cfg = _smtp_config(resolved_via)
    identity = identity_for_company_type(company.company_type if company else None)
    if not cfg["hostname"] or not cfg["username"] or not cfg["password"]:
        return {"ok": False, "message": f"{resolved_via.upper()} SMTP credentials are incomplete. Check Settings."}
    attach_resume = attach_resume and not is_client_type(company.company_type if company else None)
    if attach_resume and not resume_exists():
        return {"ok": False, "message": "Resume PDF is missing. Upload static/assets/resume.pdf before attaching it."}
    warning_message = deliverability_warning_message(email)
    if warning_message:
        return {"ok": False, "message": f"Fix deliverability warnings before sending: {warning_message}"}
    # Volume, not per-message content, is what burned the domain in May: 183 sends
    # in a single day from a cold domain. The 3-5s inter-send delay does nothing
    # about that, so the cap is enforced here, on the single-send path every send
    # goes through — including individual sends made while Safe Mode blocks batches.
    quota = daily_quota_state(db)
    if quota["exhausted"]:
        return {
            "ok": False,
            "message": (
                f"Daily send limit reached ({quota['used']}/{quota['limit']}). "
                "Raise DAILY_SEND_LIMIT in Settings or continue tomorrow."
            ),
        }

    # Envelope sender MUST equal From header to pass SPF / DMARC checks.
    from_addr = identity["from_email"]
    body = ensure_signature(email.body, company.company_type if company else None)

    msg = _build_mime(identity["from_name"], from_addr, to_addr, email.subject, body, attach_resume=attach_resume)

    send_result = await _send_smtp_message(
        msg,
        cfg=cfg,
        sender_type=resolved_via,
        from_addr=from_addr,
        to_addr=to_addr,
    )
    if not send_result["ok"]:
        return send_result

    now = datetime.utcnow()
    email.status = "sent"
    email.sent_at = now
    email.from_address = from_addr  # record which account was actually used
    email.body = body

    db.add(OutreachRecord(
        company_id=email.company_id,
        email_id=email.id,
        status="sent",
        sent_at=now,
        follow_up_date=now + timedelta(days=FOLLOW_UP_DAYS),
        created_at=now,
    ))
    db.commit()

    return {"ok": True, "message": f"SMTP accepted campaign message to {to_addr} via {resolved_via.upper()} SMTP."}


async def send_test_email(
    recipient_email: str,
    via: str,
    subject: str,
    body: str,
    attach_resume: bool = False,
) -> dict:
    recipient_email = (recipient_email or "").strip()
    subject = (subject or "").strip()
    body = (body or "").strip()

    if not recipient_email:
        return {"ok": False, "message": "Recipient email is required."}
    if via not in {"gmail", "custom"}:
        return {"ok": False, "message": "Sender type must be gmail or custom."}
    if not subject:
        return {"ok": False, "message": "Subject is required."}
    if not body:
        return {"ok": False, "message": "Body is required."}

    cfg = _smtp_config(via)
    if not cfg["hostname"] or not cfg["username"] or not cfg["password"]:
        return {"ok": False, "message": f"{via.upper()} SMTP credentials are incomplete. Check Settings."}
    if attach_resume and not resume_exists():
        return {"ok": False, "message": "Resume PDF is missing. Upload static/assets/resume.pdf before attaching it."}

    identity = identity_for_company_type("agency" if via == "gmail" else "client")
    body = ensure_signature(body, "agency" if via == "gmail" else "client")

    msg = _build_mime(
        identity["from_name"],
        identity["from_email"],
        recipient_email,
        subject,
        body,
        attach_resume=attach_resume,
    )

    send_result = await _send_smtp_message(
        msg,
        cfg=cfg,
        sender_type=via,
        from_addr=identity["from_email"],
        to_addr=recipient_email,
    )
    if not send_result["ok"]:
        return send_result

    from_header = msg.get("From")
    reply_to = msg.get("Reply-To")
    message_date = msg.get("Date")
    envelope_sender = identity["from_email"]
    smtp_host = cfg["hostname"]
    message = (
        f"SMTP accepted the message. Check inbox, spam, and Gmail Show Original for SPF/DKIM/DMARC. "
        f"Sender: {via.upper()} SMTP. From: {identity['from_email']}. To: {recipient_email}. "
        f"Message-ID: {send_result['message_id']}."
    )
    return {
        "ok": True,
        "message": message,
        "sender_type": via,
        "smtp_host": smtp_host,
        "from_email": identity["from_email"],
        "from_header": from_header,
        "envelope_sender": envelope_sender,
        "reply_to": reply_to,
        "recipient": recipient_email,
        "message_id": send_result["message_id"],
        "date": message_date,
        "provider_response": send_result.get("provider_response"),
        "show_original_instructions": "Open Gmail > Show original > check SPF, DKIM, DMARC.",
    }


# ─── Send batch (rate-limited) ────────────────────────────────────────────────

async def send_batch(email_ids: list[int], via: str, db: Session, attach_resume: bool = False) -> dict:
    """
    Send multiple emails with a 3–5 s random delay between each send.
    The delay mimics human sending cadence and avoids tripping spam filters
    that flag sudden bursts of identical-sender traffic.
    """
    if deliverability_safe_mode_enabled():
        return {
            "ok": False,
            "sent": 0,
            "failed": len(email_ids),
            "errors": ["Safe Mode is ON: batch sending is blocked, individual reviewed sends are allowed."],
        }

    sent = failed = 0
    errors: list[str] = []

    for i, eid in enumerate(email_ids):
        result = await send_email(eid, via, db, attach_resume=attach_resume)
        if result["ok"]:
            sent += 1
        else:
            failed += 1
            errors.append(result["message"])

        # Apply delay between sends — skip after the final email
        if i < len(email_ids) - 1:
            await asyncio.sleep(random.uniform(3.0, 5.0))

    return {"ok": failed == 0, "sent": sent, "failed": failed, "errors": errors[:5]}


# ─── Sample builder (for preview endpoint) ───────────────────────────────────

def build_sample_message() -> MIMEMultipart:
    """
    Return a fully-built sample MIME message for a fictional agency.
    Used by the /api/send/sample preview endpoint. The sign-off comes from
    the mailbox configured on this computer.
    """
    identity = identity_for_company_type("client")

    subject = "Collaborating on Digital Studio's React builds"
    body = (
        "Hi Sarah,\n\n"
        "Your work on the Digital Studio platform caught my attention — the React-powered "
        "dashboard you shipped last quarter handles complex state without sacrificing load time. "
        "That kind of architecture takes real care to get right.\n\n"
        "I help teams with overflow development when a project needs an extra pair of hands. "
        "Happy to share a short example if useful.\n\n"
        "Worth a 15-minute call this week to see if there is a fit?"
    )
    return _build_mime(
        identity["from_name"],
        identity["from_email"],
        "hello@digitalstudio.com.au",
        subject,
        ensure_signature(body, "client"),
    )
