from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from models import Company, DoNotContact, Email, OutreachRecord


def normalize_company_name(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def domain_from_url(url: str) -> str:
    if not url:
        return ""
    raw = url.strip()
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = (parsed.netloc or parsed.path or "").lower().strip()
    if host.startswith("www."):
        host = host[4:]
    if ":" in host:
        host = host.split(":", 1)[0]
    return host


def _domain_from_email(email: str) -> str:
    email = normalize_email(email)
    return email.split("@", 1)[1] if "@" in email else ""


def _clean_domain(value: str) -> str:
    value = (value or "").strip().lower()
    return domain_from_url(value) if value else ""


def find_do_not_contact_match(
    db: Session,
    *,
    company_name: str = "",
    email: str = "",
    domain: str = "",
) -> DoNotContact | None:
    normalized_name = normalize_company_name(company_name)
    normalized_email = normalize_email(email)
    normalized_domain = _clean_domain(domain)

    filters = []
    if normalized_email:
        filters.append(func.lower(DoNotContact.email) == normalized_email)
    if normalized_domain:
        filters.append(func.lower(DoNotContact.domain) == normalized_domain)
    if normalized_name:
        filters.append(func.lower(DoNotContact.company_name) == normalized_name)

    if not filters:
        return None

    return (
        db.query(DoNotContact)
        .filter(or_(*filters))
        .order_by(DoNotContact.created_at.desc())
        .first()
    )


def get_company_dnc_match(db: Session, company: Company | None) -> DoNotContact | None:
    if not company:
        return None
    return find_do_not_contact_match(
        db,
        company_name=company.name,
        email=company.email or "",
        domain=company.website or "",
    )


def serialize_dnc_entry(entry: DoNotContact | None) -> dict | None:
    if not entry:
        return None
    return {
        "id": entry.id,
        "email": entry.email,
        "domain": entry.domain,
        "company_name": entry.company_name,
        "reason": entry.reason,
        "source": entry.source,
        "notes": entry.notes,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


def upsert_do_not_contact(
    db: Session,
    *,
    company_name: str = "",
    email: str = "",
    domain: str = "",
    reason: str,
    source: str = "",
    notes: str = "",
) -> DoNotContact:
    normalized_name = normalize_company_name(company_name)
    normalized_email = normalize_email(email)
    normalized_domain = _clean_domain(domain)

    entry = find_do_not_contact_match(
        db,
        company_name=normalized_name,
        email=normalized_email,
        domain=normalized_domain,
    )
    if not entry:
        entry = DoNotContact(
            company_name=normalized_name or None,
            email=normalized_email or None,
            domain=normalized_domain or None,
            reason=reason,
            source=source,
            notes=notes or None,
            created_at=datetime.utcnow(),
        )
        db.add(entry)
    else:
        if normalized_name:
            entry.company_name = normalized_name
        if normalized_email:
            entry.email = normalized_email
        if normalized_domain:
            entry.domain = normalized_domain
        entry.reason = reason
        entry.source = source or entry.source
        entry.notes = notes or entry.notes
    db.commit()
    db.refresh(entry)
    return entry


def mark_company_do_not_contact(
    db: Session,
    *,
    company: Company,
    reason: str,
    source: str,
    notes: str = "",
    outreach_record: OutreachRecord | None = None,
    email: Email | None = None,
) -> DoNotContact:
    entry = upsert_do_not_contact(
        db,
        company_name=company.name,
        email=company.email or "",
        domain=company.website or "",
        reason=reason,
        source=source,
        notes=notes,
    )

    if outreach_record:
        outreach_record.status = "closed"
        extra = f"Do not contact: {reason}"
        outreach_record.notes = f"{outreach_record.notes}\n{extra}".strip() if outreach_record.notes else extra

    if email and email.status in {"pending", "approved"}:
        email.status = "discarded"

    db.commit()
    return entry


def domain_or_email_block_reason(company: Company | None, db: Session) -> str | None:
    entry = get_company_dnc_match(db, company)
    if not entry:
        return None
    reason = entry.reason.replace("_", " ")
    return f"Do not contact: {reason}"


def company_or_candidate_is_blocked(
    db: Session,
    *,
    company: Company | None = None,
    company_name: str = "",
    email: str = "",
    domain: str = "",
) -> tuple[bool, DoNotContact | None]:
    if company:
        entry = get_company_dnc_match(db, company)
    else:
        entry = find_do_not_contact_match(db, company_name=company_name, email=email, domain=domain)
    return bool(entry), entry
