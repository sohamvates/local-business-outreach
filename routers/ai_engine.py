import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from models import Company, Email
from services.ai_service import generate_for_company, generate_batch
from services.ai_service import _company_is_eligible_for_ai, _domain_from_url, _normalized_email
from services.job_store_service import get_job, set_job

router = APIRouter(prefix="/api/ai", tags=["ai_engine"])

# Thread pool for running blocking DB operations in async context
_executor = ThreadPoolExecutor(max_workers=4)


class SenderContext(BaseModel):
    sender_name: str = ""
    sender_role: str = ""
    sender_company: str = ""
    sender_email: str = ""
    value_prop: str = ""


class GenerateOnePayload(BaseModel):
    sender: SenderContext = SenderContext()


class GenerateBatchPayload(BaseModel):
    company_ids: list[int]
    sender: SenderContext = SenderContext()


# ─── Batch generation (background job) ───────────────────────────────────────
# IMPORTANT: this route must be declared BEFORE /generate/{company_id}.
# FastAPI matches routes in declaration order — if the parameterised route
# comes first, "batch" gets parsed as a company_id integer and fails.

def _run_batch_blocking(company_ids: list[int], sender: dict, job_id: str) -> None:
    """Blocking wrapper for batch generation — runs in thread executor."""
    db = SessionLocal()
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(generate_batch(company_ids, sender, job_id, db))
        finally:
            loop.close()
    except Exception as e:
        set_job(job_id, {"status": "error", "progress": 0, "message": str(e)})
    finally:
        db.close()


async def _batch_job(company_ids: list[int], sender: dict, job_id: str) -> None:
    """Runs in background — executes blocking DB ops in thread pool."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(_executor, _run_batch_blocking, company_ids, sender, job_id)


@router.post("/generate/batch")
async def generate_emails_batch(payload: GenerateBatchPayload, background_tasks: BackgroundTasks):
    if not payload.company_ids:
        return {"ok": False, "message": "No company IDs provided."}
    job_id = uuid.uuid4().hex[:8]
    set_job(job_id, {"status": "queued", "progress": 0, "message": "Queued…"})
    background_tasks.add_task(_batch_job, payload.company_ids, payload.sender.model_dump(), job_id)
    return {"ok": True, "job_id": job_id}


# ─── Single generation ────────────────────────────────────────────────────────

@router.post("/generate/{company_id}")
async def generate_email(
    company_id: int,
    payload: GenerateOnePayload,
    db: Session = Depends(get_db),
):
    company = db.get(Company, company_id)
    if not company:
        return {"ok": False, "message": "Company not found."}
    try:
        email = await generate_for_company(company, payload.sender.model_dump(), db)
        return {"ok": True, "email_id": email.id, "subject": email.subject}
    except Exception as e:
        return {"ok": False, "message": str(e)}


@router.get("/job/{job_id}")
def get_job_status(job_id: str):
    job = get_job(job_id)
    if job:
        return job
    return {"status": "not_found", "progress": 0, "message": "Job not found."}


# ─── Company list for the UI ──────────────────────────────────────────────────

@router.get("/companies")
def list_companies_for_ai(db: Session = Depends(get_db)):
    """
    All scraped companies for the AI engine page.
    Only eligible companies are returned so users cannot generate duplicate drafts.
    """
    all_companies = db.query(Company).order_by(Company.created_at.desc()).all()
    result = []
    stats = {
        "eligible_companies": 0,
        "excluded_already_contacted": 0,
        "excluded_already_has_draft": 0,
        "excluded_no_email": 0,
        "excluded_do_not_contact": 0,
    }

    seen_domains: set[str] = set()
    seen_emails: set[str] = set()

    for c in all_companies:
        eligible, reason = _company_is_eligible_for_ai(c, seen_domains, seen_emails, db)
        if not eligible:
            if reason == "already_contacted":
                stats["excluded_already_contacted"] += 1
            elif reason == "already_has_draft":
                stats["excluded_already_has_draft"] += 1
            elif reason == "no_email":
                stats["excluded_no_email"] += 1
            elif reason == "do_not_contact":
                stats["excluded_do_not_contact"] += 1
            continue

        email = _normalized_email(c.email)
        domain = _domain_from_url(c.website or "")
        if email:
            seen_emails.add(email)
        if domain:
            seen_domains.add(domain)

        stats["eligible_companies"] += 1
        result.append({
            "id": c.id,
            "name": c.name,
            "website": c.website,
            "email": c.email,
            "type": c.company_type,
            "has_email": bool(c.email and c.email.strip()),
            "has_draft": any(e.status in ("pending", "approved") for e in c.emails),
        })
    return {"companies": result, "stats": stats}
