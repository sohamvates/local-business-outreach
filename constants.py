"""
Centralized constants and enums for the outreach system.
Replace magic strings with type-safe constants.
"""
from enum import Enum


class CompanyType(str, Enum):
    """Company classification for routing and UI filtering."""
    AGENCY = "agency"
    CLIENT = "client"
    POTENTIAL_CLIENT = "potential_client"


class EmailStatus(str, Enum):
    """Email draft lifecycle states."""
    PENDING = "pending"
    APPROVED = "approved"
    DISCARDED = "discarded"
    SENT = "sent"


class OutreachStatus(str, Enum):
    """Outreach record tracking states."""
    SENT = "sent"
    REPLIED = "replied"
    FOLLOW_UP = "follow_up"
    CLOSED = "closed"


class ScraperSource(str, Enum):
    """Lead source tracking."""
    GOOGLE_MAPS = "google_maps"
    SCRAPER_AGENCIES = "scraper_agencies"


# Valid status transitions for validation
VALID_EMAIL_STATUSES = {s.value for s in EmailStatus}
VALID_OUTREACH_STATUSES = {s.value for s in OutreachStatus}
VALID_COMPANY_TYPES = {t.value for t in CompanyType}

# Status sets for deduplication logic
CONTACTED_EMAIL_STATUSES = {EmailStatus.PENDING.value, EmailStatus.APPROVED.value, EmailStatus.SENT.value}
CONTACTED_OUTREACH_STATUSES = {OutreachStatus.SENT.value, OutreachStatus.REPLIED.value, OutreachStatus.FOLLOW_UP.value, OutreachStatus.CLOSED.value}
