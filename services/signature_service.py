"""
Email identity and signature helpers.

Drafts in the Review Queue store the final visible signature so the user can
review exactly what will be sent. Sending revalidates the signature but does
not add a second one.

Silabs — Sacred Intelligence Labs — https://sacredintelligencelabs.com.au
"""
from pathlib import Path

from sqlalchemy.orm import Session

from models import Email

CLIENT_TYPES = {"client", "potential_client"}


def is_client_type(company_type: str | None) -> bool:
    return (company_type or "").strip().lower() in CLIENT_TYPES


def _mailbox_prefix(company_type: str | None) -> str:
    return "CUSTOM" if is_client_type(company_type) else "GMAIL"


def _configured_identity(company_type: str | None) -> dict:
    """
    Who the email is from when no setup profile exists.

    The name and address come from the mailbox saved in Settings. The program
    does not ship a company name, a phone number, or a website.
    """
    from services.settings_service import get_raw

    prefix = _mailbox_prefix(company_type)
    name = (get_raw(f"{prefix}_FROM_NAME") or "").strip()
    email = (get_raw(f"{prefix}_SMTP_USER") or "").strip()
    shown_name = name or "Your name"
    signature = "\n".join(line for line in (name, email) if line)
    if is_client_type(company_type):
        value_prop = (
            "Offer practical help that matches the sender's own business. "
            "Do not invent services, prices, a phone number, or a website."
        )
        tone = "direct, local, and specific to the business"
    else:
        value_prop = (
            "Offer overflow help only in the skills the sender actually has. "
            "Do not invent a technology stack, a client, or a result."
        )
        tone = "professional, concise, and low-pressure"
    return {
        "from_name": shown_name,
        "from_email": email,
        "sender_name": shown_name,
        "sender_role": "",
        "sender_company": name,
        "sender_email": email,
        "signature": signature,
        "value_prop": value_prop,
        "tone": tone,
    }


def _legacy_signature_blocks() -> list[str]:
    """
    Older signatures saved only on this computer, in legacy_signatures.txt.

    That file is never part of the public project. Review uses it to replace
    an old sign-off on drafts that have not been sent. A new install has no
    file, so this returns nothing.
    """
    path = Path(__file__).resolve().parent.parent / "legacy_signatures.txt"
    if not path.is_file():
        return []
    blocks: list[str] = []
    current: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() == "---":
            block = "\n".join(current).strip()
            if block:
                blocks.append(block)
            current = []
            continue
        current.append(line)
    tail = "\n".join(current).strip()
    if tail:
        blocks.append(tail)
    return blocks


def signature_for_company_type(company_type: str | None) -> str:
    from services.profile_service import profile_identity

    identity = profile_identity()
    if identity and identity.get("signature"):
        return identity["signature"]
    return _configured_identity(company_type)["signature"]


def identity_for_company_type(company_type: str | None) -> dict:
    from services.profile_service import profile_identity

    identity = profile_identity()
    if identity:
        return identity
    return _configured_identity(company_type)


def _blocks_to_recognise() -> list[str]:
    from services.profile_service import profile_identity

    blocks = [
        signature_for_company_type("client"),
        signature_for_company_type("agency"),
    ]
    identity = profile_identity()
    if identity and identity.get("signature"):
        blocks.append(identity["signature"])
    blocks.extend(_legacy_signature_blocks())
    unique = {block for block in blocks if block}
    return sorted(unique, key=len, reverse=True)


def has_known_signature(body: str | None) -> bool:
    text = body or ""
    return any(block in text for block in _blocks_to_recognise())


def strip_known_signature(body: str | None) -> str:
    text = (body or "").rstrip()
    for signature in _blocks_to_recognise():
        if text.endswith(signature):
            return text[: -len(signature)].rstrip()
    return text


def ensure_signature(body: str | None, company_type: str | None) -> str:
    core = strip_known_signature(body)
    signature = signature_for_company_type(company_type)
    if not signature:
        return core
    return f"{core}\n\n{signature}".strip()


def refresh_signatures(db: Session) -> int:
    """
    Re-apply the current signature to every draft that has not been sent.

    Drafts written before a mailbox change would otherwise keep the old block.
    ensure_signature() strips the known signature before appending, so this is
    safe to run on every load. Sent emails stay as they were sent.
    """
    emails = (
        db.query(Email)
        .filter(Email.status.in_(("pending", "approved")))
        .all()
    )
    changed = 0
    for email in emails:
        if not email.company:
            continue
        company_type = email.company.company_type
        updated = ensure_signature(email.body, company_type)
        if updated != email.body:
            email.body = updated
            email.from_address = identity_for_company_type(company_type)["from_email"]
            changed += 1
    if changed:
        db.commit()
    return changed


def count_pending_without_signature(db: Session) -> int:
    return len(pending_without_signature(db))


def pending_without_signature(db: Session) -> list[Email]:
    emails = db.query(Email).filter(Email.status == "pending").all()
    return [email for email in emails if email.company and not has_known_signature(email.body)]


def update_pending_without_signature(db: Session) -> int:
    emails = pending_without_signature(db)
    for email in emails:
        email.body = ensure_signature(email.body, email.company.company_type)
        email.from_address = identity_for_company_type(email.company.company_type)["from_email"]
    db.commit()
    return len(emails)
