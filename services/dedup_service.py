"""
Deduplication helpers — shared by scrapers, AI generation, and sending.

Checks:
  1. By place_id      (Google Maps canonical ID — strongest signal)
  2. By website domain (normalised, strips www.)
  3. By email address  (normalised lowercase)
  4. By contact history on the matched record
"""
import re
from urllib.parse import unquote, urlparse

from sqlalchemy.orm import Session

from models import Company
from services.do_not_contact_service import find_do_not_contact_match

CONTACT_EMAIL_STATUSES = {"pending", "approved", "sent"}
CONTACT_OUTREACH_STATUSES = {"sent", "replied", "follow_up", "closed"}

_EMAIL_SHAPE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def sanitize_scraped_email(raw: str) -> str:
    """
    Clean an address taken from a mailto: link or from page text.

    Real pages hand us addresses we cannot use as-is:
      mailto:%20info@x.com      → percent-encoded leading space
      mailto:a@x.com,b@x.com    → several recipients in one href
      mailto:info@x.com?subject=Hi → trailing query string

    A malformed address is worse than no address: it bounces, and bounces cost
    sending reputation. Returns "" when nothing valid can be recovered, so the
    caller stores no email rather than a broken one.
    """
    if not raw:
        return ""
    addr = unquote(raw).split("?")[0]
    addr = re.split(r"[,;]", addr)[0]
    addr = addr.strip().strip("<>").strip().strip(".")
    return addr.lower() if _EMAIL_SHAPE.match(addr) else ""


def domain_from_url(url: str) -> str:
    """Extract normalised domain, e.g. 'https://www.firm.com.au/about' → 'firm.com.au'."""
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


def company_has_contact_activity(
    company: Company,
    *,
    exclude_email_id: int | None = None,
    email_statuses: set[str] | None = None,
    outreach_statuses: set[str] | None = None,
) -> bool:
    email_statuses = email_statuses or CONTACT_EMAIL_STATUSES
    outreach_statuses = outreach_statuses or CONTACT_OUTREACH_STATUSES

    for email in company.emails:
        if exclude_email_id is not None and email.id == exclude_email_id:
            continue
        if email.status in email_statuses:
            return True

    for record in company.outreach_records:
        if record.status in outreach_statuses:
            return True

    return False


def classify_company_candidate(
    db: Session,
    *,
    place_id: str = "",
    domain: str = "",
    email: str = "",
    company_name: str = "",
) -> dict:
    """
    Return a classification for a scraped company candidate.

    Reasons:
      - new
      - duplicate
      - already_contacted
    """
    place_id = (place_id or "").strip()
    domain = domain_from_url(domain)
    email = normalize_email(email)
    company_name = (company_name or "").strip()

    dnc_entry = find_do_not_contact_match(
        db,
        company_name=company_name,
        email=email,
        domain=domain,
    )
    if dnc_entry:
        return {"blocked": True, "reason": "do_not_contact", "company": None, "entry": dnc_entry}

    matches: list[Company] = []
    seen_company_ids: set[int] = set()

    def _add_match(company: Company | None):
        if company and company.id not in seen_company_ids:
            seen_company_ids.add(company.id)
            matches.append(company)

    if place_id:
        _add_match(db.query(Company).filter(Company.place_id == place_id).first())

    if domain:
        _add_match(db.query(Company).filter(Company.website.ilike(f"%{domain}%")).first())

    if email:
        _add_match(db.query(Company).filter(Company.email.ilike(email)).first())

    for company in matches:
        if company_has_contact_activity(company):
            return {"blocked": True, "reason": "already_contacted", "company": company}

    if matches:
        return {"blocked": True, "reason": "duplicate", "company": matches[0]}

    return {"blocked": False, "reason": "new", "company": None}


def is_duplicate(
    db: Session,
    *,
    place_id: str = "",
    domain: str = "",
    email: str = "",
    company_name: str = "",
) -> bool:
    return classify_company_candidate(
        db,
        place_id=place_id,
        domain=domain,
        email=email,
        company_name=company_name,
    )["blocked"]
