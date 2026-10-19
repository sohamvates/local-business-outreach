"""
Clients scraper — discovers local businesses via Google Maps Places API,
scores their digital presence, and extracts contact details.

Scoring (max 6 points):
  +3  Has a website listed in Google Places
  +2  Website loads successfully (HTTP 200)
  +1  Email address found on homepage

Categories mapped to Google Places types:
  Law Firms       → lawyer
  Dental Clinics  → dentist
  Medical Centres → doctor
  Real Estate     → real_estate_agency
  Accountants     → accounting
  Restaurants     → restaurant
  Gyms            → gym
  Tradies         → general_contractor
"""
import asyncio
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from models import Company
from services.dedup_service import classify_company_candidate, domain_from_url, sanitize_scraped_email
from services.settings_service import get_raw
from services.job_store_service import set_job
from services.http_client import google_maps_limiter, request_with_retry

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

PLACES_NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
PLACES_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
PLACES_TEXT_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"

# Category label → Places API type
CATEGORY_TYPES: dict[str, str] = {
    "Law Firms":        "lawyer",
    "Dental Clinics":   "dentist",
    "Medical Centres":  "doctor",
    "Real Estate":      "real_estate_agency",
    "Accountants":      "accounting",
    "Restaurants":      "restaurant",
    "Gyms":             "gym",
    "Tradies":          "general_contractor",
    "Contractors":      "general_contractor",
}

# Suburb → (lat, lng)
SUBURB_COORDS: dict[str, tuple[float, float]] = {
    "Brighton":    (-37.9167, 144.9993),
    "South Yarra": (-37.8405, 144.9936),
    "St Kilda":    (-37.8577, 144.9810),
    "CBD":         (-37.8136, 144.9631),
    "Richmond":    (-37.8189, 144.9985),
}

SEARCH_RADIUS_M = 2_000  # 2 km radius per suburb centre

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_SPAM_EMAIL_DOMAINS = {"example.com", "domain.com", "sentry.io", "w3.org", "schema.org"}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _api_key() -> str:
    key = get_raw("GOOGLE_MAPS_API_KEY")
    if not key:
        raise ValueError("GOOGLE_MAPS_API_KEY is not set in Settings.")
    return key


async def _fetch_nearby(
    client: httpx.AsyncClient,
    lat: float,
    lng: float,
    place_type: str,
    api_key: str,
    limit: int | None = None,
) -> tuple[list[str], str | None]:
    """Return (place_ids, error_message) from Nearby Search."""
    place_ids: list[str] = []
    params = {
        "location": f"{lat},{lng}",
        "radius": SEARCH_RADIUS_M,
        "type": place_type,
        "key": api_key,
    }
    while True:
        try:
            # Use rate limiter and retry logic for Google Maps API
            async with google_maps_limiter:
                r = await request_with_retry("GET", PLACES_NEARBY_URL, params=params, timeout=15, client=client)
                data = r.json()
        except Exception as e:
            return place_ids, f"HTTP error: {e}"

        api_status = data.get("status", "UNKNOWN")
        if api_status not in ("OK", "ZERO_RESULTS"):
            err = data.get("error_message") or api_status
            return place_ids, f"{api_status}: {err}"

        for result in data.get("results", []):
            if pid := result.get("place_id"):
                place_ids.append(pid)
                if limit and len(place_ids) >= limit:
                    return place_ids, None

        next_token = data.get("next_page_token")
        if not next_token:
            break
        # Google requires a short delay before the next-page token is valid
        await asyncio.sleep(2)
        params = {"pagetoken": next_token, "key": api_key}

    return place_ids, None


async def _fetch_text_query(
    client: httpx.AsyncClient,
    lat: float,
    lng: float,
    query: str,
    api_key: str,
    limit: int | None = None,
) -> tuple[list[str], str | None]:
    """Nearby text search for a niche that has no fixed Places type."""
    params = {
        "query": query,
        "location": f"{lat},{lng}",
        "radius": SEARCH_RADIUS_M,
        "key": api_key,
    }
    try:
        async with google_maps_limiter:
            response = await request_with_retry(
                "GET", PLACES_TEXT_URL, params=params, timeout=15, client=client
            )
            data = response.json()
    except Exception as exc:
        return [], f"HTTP error: {exc}"

    api_status = data.get("status", "UNKNOWN")
    if api_status not in ("OK", "ZERO_RESULTS"):
        err = data.get("error_message") or api_status
        return [], f"{api_status}: {err}"
    place_ids = []
    for result in data.get("results", []):
        if pid := result.get("place_id"):
            place_ids.append(pid)
            if limit and len(place_ids) >= limit:
                break
    return place_ids, None


def _active_location_coords() -> dict:
    from services.profile_service import profile_location_coords

    custom = profile_location_coords()
    return custom if custom else SUBURB_COORDS


async def _fetch_details(
    client: httpx.AsyncClient,
    place_id: str,
    api_key: str,
) -> dict:
    """Fetch Place Details for a single place_id."""
    fields = "name,website,formatted_phone_number,formatted_address,rating,user_ratings_total"
    try:
        # Use rate limiter and retry logic for Google Maps API
        async with google_maps_limiter:
            r = await request_with_retry(
                "GET",
                PLACES_DETAILS_URL,
                params={"place_id": place_id, "fields": fields, "key": api_key},
                timeout=15,
                client=client,
            )
        return r.json().get("result", {})
    except Exception:
        return {}


async def _check_website(url: str) -> tuple[bool, str | None]:
    """
    Try to load the website.
    Returns (loads_ok, email_found_or_None).
    """
    if not url:
        return False, None
    if not url.startswith("http"):
        url = "https://" + url
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=12,
        ) as c:
            r = await c.get(url)
            loads = r.status_code < 400

            # Extract email from mailto links first, then regex scan
            soup = BeautifulSoup(r.text, "html.parser")
            email = None
            for a in soup.select("a[href^='mailto:']"):
                addr = sanitize_scraped_email(a["href"].replace("mailto:", ""))
                if not addr:
                    continue
                domain = addr.split("@")[-1]
                if domain not in _SPAM_EMAIL_DOMAINS:
                    email = addr
                    break

            if not email:
                for m in _EMAIL_RE.finditer(r.text):
                    addr = sanitize_scraped_email(m.group())
                    if not addr:
                        continue
                    domain = addr.split("@")[-1]
                    if domain not in _SPAM_EMAIL_DOMAINS and not any(x in addr for x in [".png", ".jpg", ".svg"]):
                        email = addr
                        break

            return loads, email
    except Exception:
        return False, None


def _score(has_website: bool, loads: bool, has_email: bool) -> int:
    return (3 if has_website else 0) + (2 if loads else 0) + (1 if has_email else 0)


# ─── Main pipeline ────────────────────────────────────────────────────────────

async def run_clients_scrape(
    categories: list[str],
    suburbs: list[str],
    job_id: str,
    db: Session,
    max_results: int = 20,
) -> None:
    def progress(pct: int, msg: str):
        set_job(job_id, {"status": "running", "progress": pct, "message": msg})

    api_key = _api_key()

    # ── Step 1: collect place_ids ──────────────────────────────────────────────
    from services.profile_service import search_place_label

    place_label = search_place_label() or "Melbourne"
    progress(5, f"Searching Google Maps for {place_label} businesses…")

    # Known niches use a Places type. Anything else is searched by name.
    seen_types: set[str] = set()
    work: list[tuple[str, str | None]] = []
    for category in categories:
        place_type = CATEGORY_TYPES.get(category)
        if place_type:
            if place_type in seen_types:
                continue
            seen_types.add(place_type)
            work.append((category, place_type))
        elif (category or "").strip():
            work.append((category.strip(), None))
    coords_map = _active_location_coords()
    selected_coords = [(s, *coords_map[s]) for s in suburbs if s in coords_map]
    candidate_limit = max_results

    if not work or not selected_coords:
        set_job(job_id, {"status": "error", "progress": 0, "message": "No valid categories or suburbs selected."})
        return

    # Build category→label reverse mapping so we can store it on the Company
    type_to_label = {v: k for k, v in CATEGORY_TYPES.items()}

    place_id_meta: dict[str, dict] = {}  # place_id → {suburb, category_label}
    nearby_requests = 0
    nearby_raw = 0
    nearby_error: str | None = None

    async with httpx.AsyncClient() as client:
        total_combos = len(work) * len(selected_coords)
        done = 0
        for category_label, place_type in work:
            for suburb_name, lat, lng in selected_coords:
                pct = 5 + int(35 * done / max(total_combos, 1))
                progress(pct, f"Searching {category_label} in {suburb_name}…")
                nearby_requests += 1
                remaining = max(candidate_limit - len(place_id_meta), 0)
                if remaining <= 0:
                    break
                if place_type:
                    ids, err = await _fetch_nearby(
                        client, lat, lng, place_type, api_key, limit=remaining
                    )
                else:
                    ids, err = await _fetch_text_query(
                        client, lat, lng, category_label, api_key, limit=remaining
                    )
                if err:
                    nearby_error = err
                    break
                nearby_raw += len(ids)
                for pid in ids:
                    if pid not in place_id_meta:
                        place_id_meta[pid] = {
                            "suburb": suburb_name,
                            "category": type_to_label.get(place_type, category_label) if place_type else category_label,
                        }
                done += 1
                if len(place_id_meta) >= candidate_limit:
                    progress(
                        40,
                        f"Collected {len(place_id_meta)} candidate places (limit {candidate_limit}). Fetching details…",
                    )
                    break
            if nearby_error:
                break
            if len(place_id_meta) >= candidate_limit:
                break

    all_place_ids = list(place_id_meta.keys())
    progress(40, f"Found {len(all_place_ids)} unique places. Fetching details…")

    # ── Step 2: fetch details + check websites ─────────────────────────────────
    stats = {
        "new_saved": 0,
        "skipped_duplicates": 0,
        "skipped_already_contacted": 0,
        "skipped_do_not_contact": 0,
        "skipped_no_email": 0,
        "filtered_out": 0,
        "nearby_requests": nearby_requests,
        "nearby_raw": nearby_raw,
        "unique_places": len(all_place_ids),
    }

    if nearby_error:
        msg = f"Google Maps search failed: {nearby_error}"
        if "REQUEST_DENIED" in nearby_error:
            msg += (
                " — fix in Google Cloud Console > Credentials > your API key: "
                "allow this IP or set Application restrictions to None, and ensure Places API is enabled."
            )
        set_job(job_id, {
            "status": "error",
            "progress": 0,
            "counts": stats,
            "message": msg,
        })
        return

    if not all_place_ids:
        set_job(job_id, {
            "status": "done",
            "progress": 100,
            "counts": stats,
            "message": (
                "Done — 0 new clients. "
                f"Google Maps returned 0 places across {nearby_requests} searches. "
                "Try more categories/suburbs or increase the search radius in code."
            ),
        })
        return

    async with httpx.AsyncClient() as client:
        for i, place_id in enumerate(all_place_ids):
            if stats["new_saved"] >= max_results:
                progress(95, f"Reached max results limit ({max_results}). Stopping.")
                break
            pct = 40 + int(55 * (i + 1) / max(len(all_place_ids), 1))
            meta = place_id_meta[place_id]

            classification = classify_company_candidate(db, place_id=place_id)
            if classification["blocked"]:
                if classification["reason"] == "already_contacted":
                    stats["skipped_already_contacted"] += 1
                    progress(pct, f"[{i+1}/{len(all_place_ids)}] Already contacted — skipping.")
                elif classification["reason"] == "do_not_contact":
                    stats["skipped_do_not_contact"] += 1
                    progress(pct, f"[{i+1}/{len(all_place_ids)}] Do not contact — skipping.")
                else:
                    stats["skipped_duplicates"] += 1
                    progress(pct, f"[{i+1}/{len(all_place_ids)}] Duplicate — skipping.")
                continue

            details = await _fetch_details(client, place_id, api_key)
            if not details:
                stats["filtered_out"] += 1
                continue

            name = details.get("name", "Unknown")
            website = details.get("website", "")
            phone = details.get("formatted_phone_number", "")
            address = details.get("formatted_address", "")
            rating = details.get("rating")
            reviews_count = details.get("user_ratings_total", 0)

            progress(pct, f"[{i+1}/{len(all_place_ids)}] Checking {name}…")

            domain = domain_from_url(website)
            classification = classify_company_candidate(db, company_name=name, domain=domain)
            if classification["blocked"]:
                if classification["reason"] == "already_contacted":
                    stats["skipped_already_contacted"] += 1
                elif classification["reason"] == "do_not_contact":
                    stats["skipped_do_not_contact"] += 1
                else:
                    stats["skipped_duplicates"] += 1
                continue

            # Check website and extract email
            loads, email = await _check_website(website)

            classification = classify_company_candidate(
                db,
                company_name=name,
                domain=domain,
                email=email or "",
            )
            if classification["blocked"]:
                if classification["reason"] == "already_contacted":
                    stats["skipped_already_contacted"] += 1
                elif classification["reason"] == "do_not_contact":
                    stats["skipped_do_not_contact"] += 1
                else:
                    stats["skipped_duplicates"] += 1
                continue

            digital_score = _score(bool(website), loads, bool(email))

            db.add(Company(
                name=name,
                address=address,
                phone=phone,
                website=website,
                email=email,
                category=meta["category"],
                rating=rating,
                reviews_count=reviews_count,
                digital_score=digital_score,
                source="google_maps",
                company_type="client",
                place_id=place_id,
                created_at=datetime.utcnow(),
            ))
            stats["new_saved"] += 1
            db.commit()

    set_job(job_id, {
        "status": "done",
        "progress": 100,
        "counts": stats,
        "message": (
            "Done — "
            f"new saved: {stats['new_saved']} · "
            f"skipped duplicates: {stats['skipped_duplicates']} · "
            f"skipped already contacted: {stats['skipped_already_contacted']} · "
            f"skipped do-not-contact: {stats['skipped_do_not_contact']} · "
            f"skipped no email: {stats['skipped_no_email']} · "
            f"filtered out: {stats['filtered_out']}."
        ),
    })
