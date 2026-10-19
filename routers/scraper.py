import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from models import Company
from services.agencies_scraper_service import (
    DEFAULT_MAX_AGENCIES,
    LOCATIONS as AGENCY_LOCATIONS,
    run_agencies_scrape,
)
from services.clients_scraper_service import (
    CATEGORY_TYPES,
    SUBURB_COORDS,
    run_clients_scrape,
)
from services.job_store_service import get_job, set_job

router = APIRouter(prefix="/api/scraper", tags=["scraper"])

# Thread pool for running blocking DB operations in async context
_executor = ThreadPoolExecutor(max_workers=4)


# ─── Agencies ─────────────────────────────────────────────────────────────────

class ScrapePayload(BaseModel):
    keywords: list[str] = ["React", "Next.js", "AI", "WordPress"]
    locations: list[str] = ["Queensland", "Gold Coast", "NSW", "Melbourne"]
    max_results: int = DEFAULT_MAX_AGENCIES


def _run_scrape_blocking(
    keywords: list[str],
    job_id: str,
    locations: list[str],
    max_results: int,
) -> None:
    """Blocking wrapper for agencies scrape — runs in thread executor."""
    db = SessionLocal()
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                run_agencies_scrape(
                    keywords,
                    job_id,
                    db,
                    locations=locations,
                    max_results=max_results,
                )
            )
        finally:
            loop.close()
    except Exception as e:
        set_job(job_id, {"status": "error", "progress": 0, "message": str(e)})
    finally:
        db.close()


async def _scrape_job(
    keywords: list[str],
    job_id: str,
    locations: list[str],
    max_results: int,
) -> None:
    """Runs in background — executes blocking DB ops in thread pool."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        _executor, _run_scrape_blocking, keywords, job_id, locations, max_results
    )


@router.post("/agencies/scrape")
async def scrape_agencies(payload: ScrapePayload, background_tasks: BackgroundTasks):
    if not payload.keywords:
        return {"ok": False, "message": "Select at least one keyword filter."}
    # Validate locations against known set; ignore unknown silently
    valid_locations = [loc for loc in payload.locations if loc in AGENCY_LOCATIONS]
    # Clamp max_results to a sane range
    max_results = max(1, min(payload.max_results, 100))
    job_id = uuid.uuid4().hex[:8]
    set_job(job_id, {"status": "queued", "progress": 0, "message": "Queued…"})
    background_tasks.add_task(
        _scrape_job, payload.keywords, job_id, valid_locations, max_results
    )
    return {
        "ok": True,
        "job_id": job_id,
        "locations": valid_locations,
        "max_results": max_results,
    }


@router.get("/meta/agency-locations")
def list_agency_locations():
    from services.profile_service import profile_city_names

    cities = profile_city_names()
    return cities if cities else list(AGENCY_LOCATIONS.keys())


@router.get("/agencies/job/{job_id}")
def get_job_status(job_id: str):
    job = get_job(job_id)
    if job:
        return job
    return {"status": "not_found", "progress": 0, "message": "Job not found."}


def _page(query, page: int | None, page_size: int | None, serialize):
    """Return one page when asked. Without a page, keep the full list."""
    if page is None:
        return [serialize(row) for row in query.all()]
    size = min(24, max(1, page_size or 9))
    page = max(1, page)
    total = query.order_by(None).count()
    pages = max(1, (total + size - 1) // size) if total else 1
    if page > pages:
        page = pages
    rows = query.offset((page - 1) * size).limit(size).all() if total else []
    return {
        "items": [serialize(row) for row in rows],
        "total": total,
        "page": page,
        "page_size": size,
        "pages": pages,
    }


@router.get("/agencies")
def list_agencies(
    page: int | None = Query(default=None),
    page_size: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(Company).filter(Company.company_type == "agency").order_by(Company.created_at.desc())
    return _page(query, page, page_size, _serialize_agency)


@router.delete("/agencies/{company_id}")
def delete_agency(company_id: int, db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    if not company:
        return {"ok": False, "message": "Not found."}
    db.delete(company)
    db.commit()
    return {"ok": True}


# ─── Clients ──────────────────────────────────────────────────────────────────

class ClientSearchPayload(BaseModel):
    categories: list[str] = list(CATEGORY_TYPES.keys())
    suburbs: list[str] = list(SUBURB_COORDS.keys())


def _run_clients_blocking(categories: list[str], suburbs: list[str], job_id: str, max_results: int) -> None:
    """Blocking wrapper for clients scrape — runs in thread executor."""
    db = SessionLocal()
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_clients_scrape(categories, suburbs, job_id, db, max_results=max_results))
        finally:
            loop.close()
    except Exception as e:
        set_job(job_id, {"status": "error", "progress": 0, "message": str(e)})
    finally:
        db.close()


async def _clients_job(categories: list[str], suburbs: list[str], job_id: str, max_results: int) -> None:
    """Runs in background — executes blocking DB ops in thread pool."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(_executor, _run_clients_blocking, categories, suburbs, job_id, max_results)


@router.post("/clients/search")
async def search_clients(payload: ClientSearchPayload, background_tasks: BackgroundTasks):
    from services.settings_service import get_raw
    if not payload.categories:
        return {"ok": False, "message": "Select at least one category."}
    if not payload.suburbs:
        return {"ok": False, "message": "Select at least one suburb."}
    try:
        max_results = int(get_raw("CLIENTS_MAX_RESULTS") or 20)
    except ValueError:
        max_results = 20
    job_id = uuid.uuid4().hex[:8]
    set_job(job_id, {"status": "queued", "progress": 0, "message": "Queued…"})
    background_tasks.add_task(_clients_job, payload.categories, payload.suburbs, job_id, max_results)
    return {"ok": True, "job_id": job_id, "max_results": max_results}


@router.get("/clients/job/{job_id}")
def get_clients_job_status(job_id: str):
    job = get_job(job_id)
    if job:
        return job
    return {"status": "not_found", "progress": 0, "message": "Job not found."}


@router.get("/clients")
def list_clients(
    page: int | None = Query(default=None),
    page_size: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Company)
        .filter(Company.company_type == "client")
        .order_by(Company.created_at.desc())
    )
    return _page(query, page, page_size, _serialize_client)


@router.delete("/clients/{company_id}")
def delete_client(company_id: int, db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    if not company or company.company_type != "client":
        return {"ok": False, "message": "Not found."}
    db.delete(company)
    db.commit()
    return {"ok": True}


@router.get("/meta/categories")
def list_categories():
    from services.profile_service import profile_niches

    niches = profile_niches()
    if niches:
        return niches
    return [name for name in CATEGORY_TYPES if name != "Contractors"]


@router.get("/meta/suburbs")
def list_suburbs():
    from services.profile_service import profile_city_names

    cities = profile_city_names()
    return cities if cities else list(SUBURB_COORDS.keys())


# ─── Serialisation ────────────────────────────────────────────────────────────

def _serialize_agency(c: Company) -> dict:
    import json
    stack = []
    if c.stack_keywords:
        try:
            stack = json.loads(c.stack_keywords)
        except Exception:
            pass
    return {
        "id": c.id,
        "name": c.name,
        "website": c.website,
        "email": c.email,
        "category": c.category,
        "rating": c.rating,
        "digital_score": c.digital_score,
        "source": c.source,
        "company_type": c.company_type,
        "stack": stack,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _serialize_client(c: Company) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "address": c.address,
        "phone": c.phone,
        "website": c.website,
        "email": c.email,
        "category": c.category,
        "rating": c.rating,
        "reviews_count": c.reviews_count,
        "digital_score": c.digital_score,
        "source": c.source,
        "company_type": c.company_type,
        "place_id": c.place_id,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }
