"""
AI service — fetches company websites and generates personalised outreach
emails using Claude claude-sonnet-4-6 via the Anthropic SDK.
"""
import re
from datetime import datetime

import httpx
import anthropic
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from models import Company, Email
from services.dedup_service import company_has_contact_activity
from services.do_not_contact_service import get_company_dnc_match
from services.signature_service import ensure_signature, identity_for_company_type
from services.settings_service import get_raw
from services.job_store_service import set_job

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
MODEL = "claude-sonnet-4-6"
MAX_WEBSITE_CHARS = 6_000

# ─── Deliverability — spam signals ────────────────────────────────────────────
_SPAM_WORDS = frozenset([
    "free", "guaranteed", "urgent", "winner", "click here", "act now",
    "limited time", "no cost", "risk-free", "risk free", "100%",
    "earn money", "cash bonus", "prize", "congratulations", "buy now",
    "order now", "apply now", "make money", "work from home",
    "amazing offer", "incredible deal", "dear friend", "dear winner",
    "boost conversions", "pay for itself quickly", "never fall through the cracks",
    "five-star reviews", "5-star reviews",
])
BANNED_OUTREACH_PHRASES = (
    "100%",
    "guaranteed",
    "boost conversions",
    "cost conversions",
    "pay for itself quickly",
    "never fall through the cracks",
    "five-star reviews",
    "5-star reviews",
    "quick call",
    "AI & Automation Solutions",
    "limited time",
    "click here",
)
SUBJECT_FALLBACKS = {
    "client": "Website and enquiry flow",
    "potential_client": "Website and enquiry flow",
    "agency": "Overflow development support",
}
CLIENT_SUBJECT_OPTIONS = (
    "Website and enquiry flow",
    "Quick question about your website",
    "Local website support",
)

# ─── Agency outreach — what may and may not be claimed ────────────────────────
# Skills a draft may name. Claiming a technology the sender cannot deliver
# collapses on the first call, so the prompt stays inside this list.
DELIVERABLE_STACK = (
    "WordPress (including headless), WooCommerce, Shopify, PHP, custom plugins, "
    "React, Next.js, Node.js, TypeScript, JavaScript, Python, FastAPI, "
    "REST APIs, GraphQL/Apollo, MySQL, PostgreSQL, "
    "Docker, Linux/VPS, Nginx, Cloudflare, Git/GitHub pull requests, "
    "LLM integrations (Claude/OpenAI), RAG, AI agents, "
    "n8n and workflow automation, "
    "email marketing setup and automation flows (Mailchimp, Klaviyo), "
    "Stripe and checkout/payment flows, landing pages and email capture, "
    "analytics and tracking installation (GA4, Google Ads setup, Meta Pixel, "
    "TikTok Pixel, conversion tracking), "
    "technical SEO (site structure, page speed, crawlability, schema)"
)
NEVER_CLAIM = (
    "Webflow, Laravel, AWS or Azure enterprise, C#, Kubernetes, "
    "Power Platform, model fine-tuning"
)
# The draft may offer to install a growth tool. It must not promise the
# numbers that tool would later report.
NEVER_PROMISE = (
    "any performance or marketing result — traffic growth, rankings, "
    "conversion rates, ROI, lead volume, ad campaign management, "
    "keyword research reports, or Search Console analysis"
)

_ALL_CAPS_RE    = re.compile(r"\b[A-Z]{4,}\b")
_EXCESS_PUNCT_RE = re.compile(r"([!?])\1{2,}")
_SHORT_URL_RE   = re.compile(
    r"https?://(bit\.ly|tinyurl\.com|t\.co|goo\.gl|ow\.ly|rb\.gy)/\S+",
    re.IGNORECASE,
)
_ANY_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_SUBJECT_SPAM_REPLACEMENTS = (
    (re.compile(r"\bfree\b", re.IGNORECASE), "Included"),
    (re.compile(r"\bguaranteed\b", re.IGNORECASE), "Reliable"),
    (re.compile(r"\burgent\b", re.IGNORECASE), "Timely"),
    (re.compile(r"\blimited time\b", re.IGNORECASE), "Current"),
    (re.compile(r"\bclick here\b", re.IGNORECASE), "Get in touch"),
)
_BODY_SPAM_REPLACEMENTS = (
    (re.compile(r"\bfree parking\b", re.IGNORECASE), "on-site parking"),
    (re.compile(r"\bfree wifi\b", re.IGNORECASE), "Wi-Fi included"),
    (re.compile(r"\bfree wi-fi\b", re.IGNORECASE), "Wi-Fi included"),
    (re.compile(r"\bfree\b", re.IGNORECASE), "included"),
    (re.compile(r"\bguaranteed\b", re.IGNORECASE), "reliable"),
    (re.compile(r"\burgent\b", re.IGNORECASE), "timely"),
    (re.compile(r"\bwinner\b", re.IGNORECASE), "strong fit"),
    (re.compile(r"\blimited time\b", re.IGNORECASE), "current"),
    (re.compile(r"\bclick here\b", re.IGNORECASE), "get in touch"),
    (re.compile(r"\bact now\b", re.IGNORECASE), "let me know"),
    (re.compile(r"\bno cost\b", re.IGNORECASE), "low-friction"),
    (re.compile(r"\brisk[- ]free\b", re.IGNORECASE), "straightforward"),
    (re.compile(r"\bprize\b", re.IGNORECASE), "opportunity"),
    (re.compile(r"\bcongratulations\b", re.IGNORECASE), "I noticed"),
)

CONTACTED_EMAIL_STATUSES = {"pending", "approved", "sent"}
CONTACTED_OUTREACH_STATUSES = {"sent", "replied", "follow_up", "closed"}


def _domain_from_url(url: str) -> str:
    if not url:
        return ""
    raw = url.strip()
    if "://" not in raw:
        raw = "https://" + raw
    from urllib.parse import urlparse

    parsed = urlparse(raw)
    host = (parsed.netloc or parsed.path or "").lower().strip()
    if host.startswith("www."):
        host = host[4:]
    if ":" in host:
        host = host.split(":", 1)[0]
    return host


def _normalized_email(value: str) -> str:
    return (value or "").strip().lower()


def _company_has_contact_activity(company: Company) -> bool:
    return company_has_contact_activity(
        company,
        email_statuses=CONTACTED_EMAIL_STATUSES,
        outreach_statuses=CONTACTED_OUTREACH_STATUSES,
    )


def _company_is_eligible_for_ai(
    company: Company,
    seen_domains: set[str],
    seen_emails: set[str],
    db: Session,
) -> tuple[bool, str]:
    if not company.email or not company.email.strip():
        return False, "no_email"
    if get_company_dnc_match(db, company):
        return False, "do_not_contact"
    if _company_has_contact_activity(company):
        return False, "already_contacted"
    if company.emails:
        if any(e.status in ("pending", "approved") for e in company.emails):
            return False, "already_has_draft"

    email = _normalized_email(company.email)
    if email and email in seen_emails:
        return False, "duplicate"

    domain = _domain_from_url(company.website or "")
    if domain and domain in seen_domains:
        return False, "duplicate"

    return True, "eligible"


def _sanitise_subject(subject: str) -> tuple[str, list[str]]:
    """
    Clean the subject line; return (cleaned, warnings).
    Rules:
      - Strip surrounding quotes Claude sometimes adds
      - Truncate to 60 chars at a word boundary
      - Flag common spam trigger words
    """
    warnings: list[str] = []
    subject = subject.strip().strip("\"'")

    for pattern, replacement in _SUBJECT_SPAM_REPLACEMENTS:
        subject = pattern.sub(replacement, subject)

    if len(subject) > 60:
        trimmed = subject[:57].rsplit(" ", 1)[0].rstrip(",:;")
        subject = trimmed + "…"

    spam_hits = _matched_spam_terms(subject)
    if spam_hits:
        warnings.append(f"Deliverability terms in subject: {', '.join(spam_hits)}")

    return subject, warnings


def _finalize_subject_for_company_type(subject: str, company_type: str | None) -> tuple[str, list[str]]:
    company_type = (company_type or "").strip().lower()
    subject = _remove_banned_outreach_phrases(subject or "").strip()
    if company_type in ("client", "potential_client"):
        lower = subject.lower()
        if not subject or any(phrase.lower() in lower for phrase in BANNED_OUTREACH_PHRASES):
            subject = CLIENT_SUBJECT_OPTIONS[0]
        if len(subject) > 45:
            subject = CLIENT_SUBJECT_OPTIONS[0]
    elif not subject:
        subject = SUBJECT_FALLBACKS.get(company_type, "Website and enquiry flow")
    return _sanitise_subject(subject)


def _matched_spam_terms(text: str) -> list[str]:
    lower = f" {(text or '').lower()} "
    matches: list[str] = []
    for term in sorted(_SPAM_WORDS, key=len, reverse=True):
        escaped = re.escape(term.lower()).replace(r"\ ", r"\s+")
        if re.search(rf"(?<![\w@]){escaped}(?![\w@])", lower):
            matches.append(term)
    return matches


def _remove_banned_outreach_phrases(text: str) -> str:
    cleaned = text or ""
    replacements = {
        "100%": "",
        "guaranteed": "reliable",
        "boost conversions": "improve enquiry flow",
        "cost conversions": "enquiry flow",
        "pay for itself quickly": "be worth reviewing",
        "never fall through the cracks": "are easier to track",
        "five-star reviews": "local reputation",
        "5-star reviews": "local reputation",
        "quick call": "brief chat",
        "AI & Automation Solutions": "website support",
        "limited time": "current",
        "click here": "reply",
    }
    for phrase, replacement in replacements.items():
        cleaned = re.sub(re.escape(phrase), replacement, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _limit_body_length(body: str, max_words: int = 125) -> str:
    """
    Trim the body to max_words while keeping the paragraph breaks intact.
    Cold outreach that arrives as one solid block reads as bulk mail and is
    much harder to scan on a phone, so paragraphs must survive the trim.
    """
    paragraphs = [p.strip() for p in (body or "").split("\n\n") if p.strip()]
    kept: list[str] = []
    used = 0
    for paragraph in paragraphs:
        words = paragraph.split()
        if used + len(words) > max_words:
            remainder = words[: max_words - used]
            if remainder:
                kept.append(" ".join(remainder))
            break
        kept.append(" ".join(words))
        used += len(words)
    text = "\n\n".join(kept).strip()
    return text.rstrip(",;:") if text else (body or "").strip()


def _sanitise_body(body: str) -> tuple[str, list[str]]:
    """
    Scrub spam patterns from body text; return (cleaned, warnings).
    Rules:
      - ALL CAPS words (4+ chars) → Title Case
      - Shortened URLs → "[link]"
      - Repeated punctuation (!!!, ???) → single character
    """
    warnings: list[str] = []
    initial_spam_hits = _matched_spam_terms(body)

    caps = _ALL_CAPS_RE.findall(body)
    if caps:
        body = _ALL_CAPS_RE.sub(lambda m: m.group().title(), body)

    if _SHORT_URL_RE.search(body):
        body = _SHORT_URL_RE.sub("[link]", body)

    if _EXCESS_PUNCT_RE.search(body):
        body = _EXCESS_PUNCT_RE.sub(r"\1", body)

    for pattern, replacement in _BODY_SPAM_REPLACEMENTS:
        body = pattern.sub(replacement, body)

    body = _remove_banned_outreach_phrases(body)
    spam_hits = list(dict.fromkeys(initial_spam_hits + _matched_spam_terms(body)))
    if spam_hits:
        warnings.append(f"Deliverability terms in body: {', '.join(spam_hits)}")

    return body.strip(), warnings


def _normalize_plain_text_body(body: str) -> str:
    """
    Normalize email body to plain text.
    Uses BeautifulSoup for reliable HTML stripping instead of regex.
    """
    text = (body or "").replace("\r\n", "\n").replace("\r", "\n")

    # Use BeautifulSoup for reliable HTML parsing (regex is fragile)
    if "<" in text and ">" in text:
        try:
            soup = BeautifulSoup(text, "html.parser")
            text = soup.get_text(separator=" ", strip=True)
        except Exception:
            # Fallback to regex if BeautifulSoup fails
            text = _HTML_TAG_RE.sub(" ", text)

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _strip_client_links_and_legacy_signature(body: str) -> str:
    text = _normalize_plain_text_body(body)
    text = _ANY_URL_RE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _pending_emails_needing_cleanup(db: Session) -> list[Email]:
    emails = (
        db.query(Email)
        .filter(Email.status == "pending")
        .order_by(Email.created_at.desc())
        .all()
    )
    result: list[Email] = []
    for email in emails:
        review_notes = email.review_notes or ""
        if review_notes:
            result.append(email)
    return result


def _pending_client_emails_needing_format_cleanup(db: Session) -> list[Email]:
    emails = (
        db.query(Email)
        .join(Company, Company.id == Email.company_id)
        .filter(Email.status == "pending", Company.company_type.in_(("client", "potential_client")))
        .order_by(Email.created_at.desc())
        .all()
    )
    result: list[Email] = []
    for email in emails:
        body = email.body or ""
        if "<" in body:
            result.append(email)
    return result


def _finalize_body_for_company_type(body: str, company_type: str | None) -> str:
    text = _normalize_plain_text_body(body)
    company_type = (company_type or "").lower()
    if company_type == "agency":
        return _limit_body_length(_remove_banned_outreach_phrases(text), max_words=140)

    text = _strip_client_links_and_legacy_signature(text)
    text = _remove_banned_outreach_phrases(text)
    cta = "If useful, I can send through a couple of practical notes for your site."
    if cta in text:
        return _limit_body_length(text, max_words=120)
    return _limit_body_length(f"{text}\n\n{cta}".strip(), max_words=120)


def count_pending_deliverability_fixes(db: Session) -> int:
    return len(_pending_emails_needing_cleanup(db))


def fix_pending_deliverability_issues(db: Session) -> int:
    emails = _pending_emails_needing_cleanup(db)
    for email in emails:
        subject, subj_warns = _sanitise_subject(email.subject or "")
        body, body_warns = _sanitise_body(email.body or "")
        body = _finalize_body_for_company_type(body, email.company.company_type if email.company else None)
        body = ensure_signature(body, email.company.company_type if email.company else None)
        email.subject = subject
        email.body = body
        remaining = subj_warns + body_warns
        email.review_notes = "\n".join(remaining) if remaining else None
    db.commit()
    return len(emails)


def fix_pending_client_plain_text_format(db: Session) -> int:
    emails = _pending_client_emails_needing_format_cleanup(db)
    for email in emails:
        body = _finalize_body_for_company_type(email.body or "", email.company.company_type if email.company else None)
        email.body = ensure_signature(body, email.company.company_type if email.company else None)
        if email.review_notes:
            cleaned_notes = [
                line for line in email.review_notes.splitlines()
                if "html" not in line.lower()
            ]
            email.review_notes = "\n".join(cleaned_notes).strip() or None
    db.commit()
    return len(emails)


def _get_client() -> anthropic.Anthropic:
    key = get_raw("CLAUDE_API_KEY")
    if not key:
        raise ValueError("CLAUDE_API_KEY is not configured in Settings.")
    return anthropic.Anthropic(api_key=key)


async def _fetch_website_snapshot(url: str) -> dict:
    """Fetch homepage, strip tags, return text plus final URL metadata."""
    if not url:
        return {"text": "", "final_url": "", "redirect_mismatch": False}
    if not url.startswith("http"):
        url = "https://" + url
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=12,
        ) as c:
            r = await c.get(url)
            soup = BeautifulSoup(r.text, "html.parser")
            # Remove noise
            for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
                tag.decompose()
            text = soup.get_text(separator=" ", strip=True)
            # Collapse whitespace
            text = re.sub(r"\s{2,}", " ", text)
            original_domain = _domain_from_url(url)
            final_domain = _domain_from_url(str(r.url))
            redirect_mismatch = bool(
                original_domain
                and final_domain
                and original_domain != final_domain
                and not final_domain.endswith(f".{original_domain}")
                and not original_domain.endswith(f".{final_domain}")
            )
            return {
                "text": text[:MAX_WEBSITE_CHARS],
                "final_url": str(r.url),
                "redirect_mismatch": redirect_mismatch,
            }
    except Exception:
        return {"text": "", "final_url": "", "redirect_mismatch": False}


def _build_prompt(company: Company, website_text: str, sender_context: dict) -> str:
    stack = ""
    if company.stack_keywords:
        import json
        try:
            stack_list = json.loads(company.stack_keywords)
            if stack_list:
                stack = f"Tech stack detected: {', '.join(stack_list)}."
        except Exception:
            pass

    company_specific_rules = ""
    if (company.company_type or "").lower() == "agency":
        company_specific_rules = f"""AGENCY RULES:
- Focus on subcontract or overflow development support.
- Write exactly THREE short paragraphs, separated by blank lines:
  1. One specific, verifiable observation about work THIS agency has shipped,
     taken only from the website excerpt — name a real client, project or
     service focus when the excerpt supports it. No praise, just evidence you read it.
  2. Bridge that observation to capacity (work of that standard usually keeps a
     team busy), then state availability for subcontract and overflow work,
     naming ONLY the technologies this agency actually appears to use.
     Add one line that removes hiring friction: works independently, fits into
     existing workflows, no hand-holding needed.
  3. A low-friction close offering to share a resume or a short call.
- DELIVERABLE STACK — the only technologies you may say we work with: {DELIVERABLE_STACK}.
- NEVER claim: {NEVER_CLAIM}. If the agency appears to work only in those,
  do not name any technology — refer to general full-stack and integration support instead.
- NEVER promise: {NEVER_PROMISE}. Offer to BUILD and INSTALL the growth stack
  (tracking, email flows, checkout, landing pages), never to produce the numbers it reports.
- Do not invent clients, project names, numbers or years. If the website excerpt
  carries no specific detail, keep the opener factual and general instead of guessing.
- Subject: name the specific technology or service plus the city when the excerpt
  supports it, e.g. "React dev available for overflow work".
- Keep the tone personal, professional, and low-pressure.
- You may mention immediate availability and that a resume can be shared.
- Do not sound like a sales campaign or agency pitch."""
    else:
        company_specific_rules = """CLIENT RULES:
- Write like a local business owner reaching out, not a marketing campaign.
- Mention one real observation from the business or site only when the website excerpt clearly supports it.
- Do not mention review counts, ratings, five-star reviews, or public reputation unless the user manually supplied that exact point.
- Do not overpraise the business.
- Identify one practical, modest area only if supported: website clarity, enquiry forms, booking flow, page speed, or simple admin follow-up.
- Use this CTA style near the end: "If useful, I can send through a couple of practical notes for your site."
- Keep it professional, direct, human, and plain text only."""

    return f"""You are writing a concise, personalised cold outreach email on behalf of {sender_context['sender_company']}.

SENDER CONTEXT:
- Name: {sender_context['sender_name']}
- Role: {sender_context['sender_role']}
- Company: {sender_context['sender_company']}
- Value proposition: {sender_context['value_prop']}
- Sender email: {sender_context['sender_email']}
- Outreach context: {sender_context['tone']}

TARGET COMPANY:
- Name: {company.name}
- Website: {company.website or 'unknown'}
- Type: {company.company_type or 'business'}
{stack}
- Website excerpt: {website_text or 'No website content available.'}
{company_specific_rules}

INSTRUCTIONS:
    1. Write ONE short, genuine cold outreach email in plain text only (70–120 words preferred, never over 130 words).
2. Open with a specific, personalised observation about their business only if the website excerpt clearly supports it; otherwise keep the opener general and factual.
    3. Briefly explain the relevance in modest, practical language. Do not make ROI, revenue, conversion, or growth claims.
    4. End with a low-friction CTA that asks permission to send a note or suggestion. Do not ask for a "quick call".
    5. Tone: professional, local, consultative, and conversational. Not corporate, promotional, or salesy.
6. Do NOT use filler phrases like "I hope this email finds you well" or "I came across your website".
7. Do NOT include any sign-off, name, job title, website, phone number, ABN, LinkedIn, or signature.
8. Do NOT invent contact details. The system appends the exact approved signature automatically.
    9. Avoid spam-trigger language such as free, guaranteed, urgent, winner, limited time, click here, buy now, 100%, boost conversions, pay for itself quickly, never fall through the cracks, five-star reviews, or excessive punctuation.
10. Do not use ALL CAPS.
    11. Subject: under 45 characters for clients, under 55 for agencies. For clients, prefer: "Website and enquiry flow", "Quick question about your website", or "Local website support".
12. Do not include HTML, markdown, bullets, clickable links, or URLs.
13. End the body after the CTA sentence.

Respond ONLY with valid JSON in this exact shape (no markdown fences):
{{"subject": "...", "body": "..."}}"""


def _auto_sender_context(company: Company, base_context: dict) -> dict:
    """
    Override sender identity based on company type so the right person and
    email account are used without the caller needing to know the routing rules.
    """
    ctx = dict(base_context)
    identity = identity_for_company_type(company.company_type)
    ctx["sender_name"] = identity["sender_name"]
    ctx["sender_email"] = identity["sender_email"]
    ctx["sender_role"] = identity["sender_role"]
    ctx["sender_company"] = identity["sender_company"]
    ctx["value_prop"] = identity["value_prop"]
    ctx["tone"] = identity["tone"]
    return ctx


async def generate_for_company(
    company: Company,
    sender_context: dict,
    db: Session,
) -> Email:
    """
    Fetch website, call Claude, store result as a pending Email.
    Returns the saved Email object.
    """
    if company_has_contact_activity(company):
        raise ValueError(f"{company.name} already has outreach activity or an existing draft.")
    dnc_entry = get_company_dnc_match(db, company)
    if dnc_entry:
        raise ValueError(f"{company.name} is marked do not contact: {dnc_entry.reason}.")

    # Auto-override sender identity based on company type
    sender_context = _auto_sender_context(company, sender_context)

    website_snapshot = await _fetch_website_snapshot(company.website or "")
    if website_snapshot["redirect_mismatch"]:
        raise ValueError(
            "Needs manual review: website redirects to a different domain, so personalised claims were blocked."
        )
    website_text = website_snapshot["text"]
    prompt = _build_prompt(company, website_text, sender_context)

    client = _get_client()
    message = client.messages.create(
        model=MODEL,
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()

    # Parse JSON — strip accidental code fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    import json
    parsed = json.loads(raw)
    subject = parsed.get("subject", SUBJECT_FALLBACKS.get((company.company_type or "").lower(), "Website and enquiry flow"))
    body = parsed.get("body", raw)

    # ── Deliverability sanitization ──────────────────────────
    subject, subj_warns = _finalize_subject_for_company_type(subject, company.company_type)
    body, body_warns = _sanitise_body(body)
    body = _finalize_body_for_company_type(body, company.company_type)
    body = ensure_signature(body, company.company_type)
    all_warns = subj_warns + body_warns

    email = Email(
        company_id=company.id,
        subject=subject,
        body=body,
        from_address=sender_context["sender_email"],
        status="pending",
        review_notes="\n".join(all_warns) if all_warns else None,
        created_at=datetime.utcnow(),
    )
    db.add(email)
    db.commit()
    db.refresh(email)
    return email


async def generate_batch(
    company_ids: list[int],
    sender_context: dict,
    job_id: str,
    db: Session,
) -> None:
    """Generate emails for a list of company IDs; updates job store."""
    def progress(pct: int, msg: str):
        set_job(job_id, {"status": "running", "progress": pct, "message": msg})

    progress(0, "Starting email generation…")
    generated = failed = 0
    # Per-company failures, kept so the finished job can explain itself. Progress
    # messages overwrite each other, so without this the user only ever sees
    # "N failed" and cannot tell a bad API key from an unreadable website.
    failures: list[dict] = []

    def record_failure(name: str, reason: str) -> None:
        failures.append({"company": name, "reason": reason})

    for i, cid in enumerate(company_ids):
        pct = int(100 * (i + 1) / max(len(company_ids), 1))
        company = db.get(Company, cid)
        if not company:
            failed += 1
            record_failure(f"company id {cid}", "company no longer exists")
            continue

        if company_has_contact_activity(company):
            progress(pct, f"[{i+1}/{len(company_ids)}] {company.name} — already contacted or already has a draft, skipping.")
            continue

        progress(pct, f"[{i+1}/{len(company_ids)}] Generating email for {company.name}…")
        try:
            await generate_for_company(company, sender_context, db)
            generated += 1
        except Exception as e:
            failed += 1
            record_failure(company.name, str(e))
            progress(pct, f"[{i+1}/{len(company_ids)}] {company.name} — error: {e}")

    message = f"Done — {generated} emails generated, {failed} failed."
    if failures:
        # Group identical reasons so 7 sites redirecting reads as one line, not seven.
        grouped: dict[str, int] = {}
        for f in failures:
            grouped[f["reason"]] = grouped.get(f["reason"], 0) + 1
        summary = " · ".join(f"{count}× {reason}" for reason, count in grouped.items())
        message = f"{message} Reasons: {summary}"

    set_job(job_id, {
        "status": "done",
        "progress": 100,
        "message": message,
        "failures": failures,
    })
