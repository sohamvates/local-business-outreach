"""
Agencies scraper — discovers Australian digital agencies from multiple sources,
detects their tech stack by analysing their websites, and filters by keywords.
Sources: DuckDuckGo HTML search, Clutch.co, TechBehemoths.
"""
import asyncio
import json
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from models import Company
from services.dedup_service import classify_company_candidate, domain_from_url, sanitize_scraped_email
from services.job_store_service import set_job
from services.settings_service import get_raw
from services.http_client import google_maps_limiter, request_with_retry

PLACES_TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
PLACES_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# ─── Stack fingerprints ───────────────────────────────────────────────────────
STACK_FINGERPRINTS: dict[str, list[str]] = {
    "React":     ["react-dom", "__reactfiber", "reactroot", "/static/js/main", "from 'react'", 'from "react"'],
    "Next.js":   ["__next_data__", "_next/static", "/_next/", "next/dist"],
    "Vue":       ["vue.min.js", "vue.js", "__vue__", "__vue_app__", "createapp("],
    "WordPress": ["wp-content/themes", "wp-content/plugins", "/wp-json/", "wordpress"],
    "Shopify":   ["shopify", "myshopify.com", "shopify.theme"],
    "Angular":   ["ng-version=", "angular.min.js", "zone.js", "__ngcontext__"],
    "Laravel":   ["laravel_session", "csrf-token", "laravel"],
    "Webflow":   ["webflow.com/", "wf-form-page", "data-wf-page"],
    "AI":        [
        "artificial intelligence", "machine learning", "chatbot", "openai",
        "generative ai", "llm", "large language model", "ai agency",
        "ai solutions", "ai development",
    ],
}

SEARCH_QUERIES = [
    "Australian digital agency React Next.js web development",
    "Australia web agency WordPress AI development services",
    "Melbourne Sydney digital agency React Next.js",
    "Australia agency AI machine learning web development",
]

# ─── Location filter ──────────────────────────────────────────────────────────
# Each location has aliases the page might use (city names, suburbs, state codes,
# postcode ranges) and a list of search terms used to seed DuckDuckGo queries.
LOCATIONS: dict[str, dict] = {
    "Queensland": {
        "aliases": [
            "queensland", "qld", "brisbane", "sunshine coast", "cairns",
            "townsville", "toowoomba", "ipswich", "logan",
        ],
        "queries": [
            "digital agency Brisbane Queensland",
            "Queensland web development agency",
            "QLD digital marketing agency",
        ],
        # Brisbane CBD — Places API biases results toward this point.
        "coords": (-27.4698, 153.0251),
        "places_query_suffix": "Brisbane Queensland Australia",
    },
    "Gold Coast": {
        "aliases": [
            "gold coast", "surfers paradise", "broadbeach", "burleigh",
            "robina", "southport", "coolangatta",
        ],
        "queries": [
            "Gold Coast digital agency",
            "Gold Coast web design agency",
            "Surfers Paradise web development",
        ],
        "coords": (-28.0023, 153.4145),
        "places_query_suffix": "Gold Coast Queensland Australia",
    },
    "NSW": {
        "aliases": [
            "new south wales", "nsw", "sydney", "newcastle", "wollongong",
            "central coast", "parramatta", "north sydney",
        ],
        "queries": [
            "Sydney digital agency NSW",
            "NSW web development agency",
            "Sydney AI agency",
        ],
        "coords": (-33.8688, 151.2093),
        "places_query_suffix": "Sydney NSW Australia",
    },
    "Melbourne": {
        "aliases": [
            "melbourne", "victoria", "vic", "south yarra", "richmond",
            "fitzroy", "st kilda", "carlton", "cbd melbourne",
        ],
        "queries": [
            "Melbourne digital agency",
            "Melbourne Victoria web agency",
            "Melbourne AI agency",
        ],
        "coords": (-37.8136, 144.9631),
        "places_query_suffix": "Melbourne Victoria Australia",
    },
}


def _location_info(name: str) -> dict | None:
    info = LOCATIONS.get(name)
    if info:
        return info
    from services.profile_service import city_record

    city = city_record(name)
    if not city:
        return None
    query = city.get("query") or name
    return {
        "aliases": [name.lower(), str(query).lower()],
        "queries": [f"digital agency {query}"],
        "coords": (city["lat"], city["lng"]),
        "places_query_suffix": query,
    }


# Generic agency search terms — combined with each location for Places queries.
PLACES_AGENCY_TERMS = [
    "digital agency",
    "web design agency",
    "marketing agency",
    "advertising agency",
    "creative agency",
]

# Default cap so a single scrape doesn't run away.
DEFAULT_MAX_AGENCIES = 25

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_SPAM_DOMAINS = {"example.com", "domain.com", "sentry.io", "w3.org", "schema.org"}
_DIRECTORY_DOMAINS = {
    "bestplacestohire.com",
    "clutch.co",
    "designrush.com",
    "goodfirms.co",
    "sortlist.com",
    "techbehemoths.com",
    "themanifest.com",
    "upcity.com",
}
_BLOCKED_PAGE_TITLES = {
    "access denied",
    "attention required",
    "forbidden",
    "just a moment",
}


# ─── HTTP helpers ─────────────────────────────────────────────────────────────
def _headers() -> dict:
    return {"User-Agent": USER_AGENT, "Accept-Language": "en-AU,en;q=0.9"}


async def _get(client: httpx.AsyncClient, url: str, **kw) -> httpx.Response | None:
    try:
        return await client.get(url, **kw)
    except Exception:
        return None


async def _fetch_page(url: str) -> str:
    if not url:
        return ""
    if not url.startswith("http"):
        url = "https://" + url
    try:
        async with httpx.AsyncClient(headers=_headers(), follow_redirects=True, timeout=12) as c:
            r = await c.get(url)
            return r.text[:80_000]
    except Exception:
        return ""


# ─── Source scrapers ──────────────────────────────────────────────────────────
async def _ddg_search(query: str) -> list[str]:
    """DuckDuckGo HTML endpoint — no API key needed."""
    try:
        async with httpx.AsyncClient(headers=_headers(), follow_redirects=True, timeout=15) as c:
            r = await c.post("https://html.duckduckgo.com/html/", data={"q": query, "kl": "au-en"})
            soup = BeautifulSoup(r.text, "html.parser")
            return [
                a["href"] for a in soup.select("a.result__a")
                if a.get("href", "").startswith("http") and "duckduckgo" not in a["href"]
            ][:8]
    except Exception:
        return []


async def _scrape_clutch() -> list[dict]:
    results = []
    async with httpx.AsyncClient(headers=_headers(), follow_redirects=True, timeout=15) as c:
        for page in range(0, 3):
            r = await _get(c, f"https://clutch.co/au/agencies/digital?page={page}")
            if not r or r.status_code != 200:
                break
            soup = BeautifulSoup(r.text, "html.parser")
            for card in soup.select("li.providers__item, li.provider-row"):
                name_el = card.select_one("h3 a, .company-name a, .company_info h3")
                name = name_el.get_text(strip=True) if name_el else None
                site_el = card.select_one("a[title='Visit Website'], .website-link, a.website")
                website = site_el.get("href", "").strip() if site_el else ""
                if name and website:
                    results.append({"name": name, "website": website, "source": "clutch"})
    return results


async def _scrape_techbehemoths() -> list[dict]:
    results = []
    r = await _fetch_page("https://techbehemoths.com/companies/digital-agencies/australia")
    if not r:
        return results
    soup = BeautifulSoup(r, "html.parser")
    for card in soup.select("article, div[class*='company-card'], div[class*='CompanyCard']"):
        name_el = card.select_one("h2, h3, [class*='name']")
        name = name_el.get_text(strip=True) if name_el else None
        link_el = card.find("a", href=re.compile(r"^https?://(?!techbehemoths)"))
        website = link_el["href"] if link_el else ""
        if name and len(name) > 2:
            results.append({"name": name, "website": website, "source": "techbehemoths"})
    return results


# ─── Analysers ────────────────────────────────────────────────────────────────
def _detect_stack(html: str) -> list[str]:
    lower = html.lower()
    return [tech for tech, patterns in STACK_FINGERPRINTS.items() if any(p in lower for p in patterns)]


def _extract_email(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.select("a[href^='mailto:']"):
        addr = sanitize_scraped_email(a["href"].replace("mailto:", ""))
        if not addr:
            continue
        domain = addr.split("@")[-1]
        if domain not in _SPAM_DOMAINS:
            return addr
    for m in _EMAIL_RE.finditer(html):
        addr = sanitize_scraped_email(m.group())
        if not addr:
            continue
        domain = addr.split("@")[-1]
        if domain not in _SPAM_DOMAINS and not any(x in addr for x in [".png", ".jpg", ".svg"]):
            return addr
    return None


def _clean_title(raw: str) -> str:
    """Strip branding suffixes after |  -  –  — from page/meta titles."""
    return re.split(r"\s[|\-–—]\s|\s[|\-–—]|[|\-–—]\s", raw)[0].strip()


def _is_directory_domain(url: str) -> bool:
    domain = domain_from_url(url)
    return any(domain == blocked or domain.endswith(f".{blocked}") for blocked in _DIRECTORY_DOMAINS)


def _is_blocked_page_name(name: str) -> bool:
    lower = (name or "").strip().lower()
    return any(title in lower for title in _BLOCKED_PAGE_TITLES)


def _places_api_key() -> str | None:
    """Return Google Places API key, or None if not configured."""
    return get_raw("GOOGLE_MAPS_API_KEY") or None


async def _places_text_search(
    query: str,
    api_key: str,
    client: httpx.AsyncClient,
    location: tuple[float, float] | None = None,
    radius_m: int = 50_000,
) -> tuple[list[dict], str | None]:
    """
    Run a Google Places Text Search.

    Returns (results, error_message). error_message is None on success or a
    string like "REQUEST_DENIED: ..." when the API rejects the call. Empty
    results with no error means the query simply matched nothing.
    """
    results: list[dict] = []
    params: dict = {"query": query, "key": api_key}
    if location:
        params["location"] = f"{location[0]},{location[1]}"
        params["radius"] = radius_m

    while True:
        try:
            async with google_maps_limiter:
                r = await request_with_retry(
                    "GET", PLACES_TEXT_SEARCH_URL, params=params, timeout=15, client=client
                )
                data = r.json()
        except Exception as e:
            return results, f"HTTP error: {e}"

        api_status = data.get("status", "UNKNOWN")
        if api_status not in ("OK", "ZERO_RESULTS"):
            err = data.get("error_message") or api_status
            return results, f"{api_status}: {err}"

        for item in data.get("results", []):
            results.append({
                "name": item.get("name"),
                "place_id": item.get("place_id"),
                "address": item.get("formatted_address"),
            })

        if len(results) >= 60:
            break

        token = data.get("next_page_token")
        if not token:
            break
        # Google requires a short delay before the next-page token activates.
        await asyncio.sleep(2)
        params = {"pagetoken": token, "key": api_key}

    return results, None


async def _places_details(
    place_id: str,
    api_key: str,
    client: httpx.AsyncClient,
) -> tuple[dict, str | None]:
    """Fetch website + phone for a single place_id via Place Details."""
    fields = "name,website,formatted_phone_number,formatted_address"
    try:
        async with google_maps_limiter:
            r = await request_with_retry(
                "GET",
                PLACES_DETAILS_URL,
                params={"place_id": place_id, "fields": fields, "key": api_key},
                timeout=15,
                client=client,
            )
        data = r.json()
    except Exception as e:
        return {}, f"HTTP error: {e}"

    api_status = data.get("status", "UNKNOWN")
    if api_status != "OK":
        err = data.get("error_message") or api_status
        return {}, f"{api_status}: {err}"

    return data.get("result", {}), None


async def _gather_places_candidates(
    locations: list[str],
    api_key: str,
) -> tuple[list[dict], str | None]:
    """
    For each selected location × each agency search term, run a Text Search and
    enrich each hit with a Details call. De-dups by place_id.

    Returns (candidates, error_message). The error stops the run early so the
    user sees the actual cause instead of "Places=0".
    """
    candidates: dict[str, dict] = {}

    async with httpx.AsyncClient(headers=_headers(), timeout=20) as client:
        for loc in locations:
            info = _location_info(loc)
            if not info:
                continue
            coords = info.get("coords")
            suffix = info.get("places_query_suffix", loc)
            for term in PLACES_AGENCY_TERMS:
                query = f"{term} {suffix}"
                results, err = await _places_text_search(
                    query, api_key, client, location=coords
                )
                if err:
                    # Bubble up immediately — config error, retrying won't help.
                    return [], err
                for item in results:
                    pid = item.get("place_id")
                    if pid and pid not in candidates:
                        candidates[pid] = {**item, "matched_location": loc}

        enriched: list[dict] = []
        for pid, item in candidates.items():
            details, err = await _places_details(pid, api_key, client)
            if err:
                return [], err
            website = (details.get("website") or "").strip()
            if not website:
                continue
            enriched.append({
                "name": details.get("name") or item.get("name") or "",
                "website": website,
                "phone": details.get("formatted_phone_number") or "",
                "source": "google_places",
                "place_id": pid,
                "address": details.get("formatted_address") or item.get("address") or "",
                "matched_location": item["matched_location"],
            })

    return enriched, None


def _matches_location(html: str, locations: list[str]) -> str | None:
    """
    Return the first matching location key if the page mentions any of its
    aliases, else None. Operates on lowercased HTML.
    """
    if not locations:
        return None
    lower = html.lower()
    for loc in locations:
        info = _location_info(loc)
        if not info:
            continue
        for alias in info["aliases"]:
            if alias in lower:
                return loc
    return None


def _build_search_queries(keywords: list[str], locations: list[str]) -> list[str]:
    """
    Build location × keyword search queries. If no locations, fall back to the
    static SEARCH_QUERIES list to preserve previous behaviour.
    """
    if not locations:
        return list(SEARCH_QUERIES)

    queries: list[str] = []
    for loc in locations:
        info = _location_info(loc)
        if not info:
            continue
        # Base location queries (location alone discovers agencies even without
        # a keyword match — keyword filter still applies on the fetched page).
        queries.extend(info["queries"])
        # Cross with each keyword for better stack-specific hits.
        for kw in keywords[:3]:  # cap to avoid query explosion
            queries.append(f"{kw} digital agency {loc}")
    # De-dup while preserving order
    seen = set()
    deduped = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            deduped.append(q)
    return deduped


def _extract_name(html: str, fallback: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for meta_prop in ("og:site_name", "og:title"):
        tag = soup.find("meta", property=meta_prop)
        if tag and tag.get("content"):
            name = _clean_title(tag["content"])
            if 2 < len(name) < 80:
                return name
    if soup.title:
        raw = soup.title.string or ""
        name = _clean_title(raw)
        if 2 < len(name) < 80:
            return name
    return fallback


# ─── Main pipeline ────────────────────────────────────────────────────────────
async def run_agencies_scrape(
    keywords: list[str],
    job_id: str,
    db: Session,
    locations: list[str] | None = None,
    max_results: int = DEFAULT_MAX_AGENCIES,
) -> None:
    locations = locations or []

    def progress(pct: int, msg: str):
        set_job(job_id, {"status": "running", "progress": pct, "message": msg})

    loc_label = ", ".join(locations) if locations else "Australia"
    progress(5, f"Searching for digital agencies in {loc_label}…")

    # ─── Primary source: Google Places Text Search ────────────────────────────
    # The previous HTML scrapers (DDG/Clutch/TechBehemoths) all return 0 because
    # they trip bot-detection / 403 / "anomaly" pages. Places API is the
    # reliable alternative and we already use it for the clients scraper.
    places_results: list[dict] = []
    places_error: str | None = None
    api_key = _places_api_key()
    if api_key and locations:
        try:
            places_results, places_error = await _gather_places_candidates(locations, api_key)
        except Exception as e:
            places_error = str(e)
    elif not api_key:
        places_error = "GOOGLE_MAPS_API_KEY not set in Settings"

    # ─── Fallback sources (best-effort) ────────────────────────────────────────
    queries = _build_search_queries(keywords, locations)
    search_tasks = [_ddg_search(q) for q in queries]
    ddg_results, clutch_results, tb_results = await asyncio.gather(
        asyncio.gather(*search_tasks),
        _scrape_clutch(),
        _scrape_techbehemoths(),
    )

    ddg_urls = [u for urls in ddg_results for u in urls]
    source_counts = {
        "places_raw": len(places_results),
        "ddg_raw": len(ddg_urls),
        "clutch_raw": len(clutch_results),
        "techbehemoths_raw": len(tb_results),
    }

    # Places results have name + website + matched_location pre-filled.
    # Clutch/TB also have name + website. DDG only has URLs.
    structured = places_results + clutch_results + tb_results

    # Build a deduplicated work list
    seen_domains: set[str] = set()
    work: list[dict] = []

    def _domain(url: str) -> str:
        return url.split("//")[-1].split("/")[0].replace("www.", "").lower()

    for item in structured:
        if _is_directory_domain(item.get("website", "")):
            continue
        d = _domain(item.get("website", item.get("name", "")))
        if d and d not in seen_domains:
            seen_domains.add(d)
            work.append(item)

    for url in ddg_urls:
        if _is_directory_domain(url):
            continue
        d = _domain(url)
        if d and d not in seen_domains:
            seen_domains.add(d)
            work.append({"name": "", "website": url, "source": "ddg"})

    # Pre-load known agency domains so we skip HTTP fetches for duplicates
    # that we'd otherwise re-fetch and then throw away.
    known_domains: set[str] = set()
    for (website,) in db.query(Company.website).filter(Company.website.isnot(None)).all():
        d = domain_from_url(website or "")
        if d:
            known_domains.add(d)

    pre_filtered: list[dict] = []
    pre_skipped = 0
    for item in work:
        d = domain_from_url(item.get("website", ""))
        if d and d in known_domains:
            pre_skipped += 1
            continue
        pre_filtered.append(item)
    work = pre_filtered

    if not work:
        bits = [
            f"Places={source_counts['places_raw']}",
            f"DDG={source_counts['ddg_raw']}",
            f"Clutch={source_counts['clutch_raw']}",
            f"TechBehemoths={source_counts['techbehemoths_raw']}",
        ]
        msg = (
            f"Done — 0 new agencies. Sources returned: {', '.join(bits)}. "
            f"Already in DB (skipped): {pre_skipped}."
        )
        if places_error:
            # Make REQUEST_DENIED actionable — it's a config issue, not a code one.
            if "REQUEST_DENIED" in places_error:
                msg += (
                    f" ⚠ Google Places blocked: {places_error} — "
                    "fix in Google Cloud Console → Credentials → your API key → "
                    "Application restrictions: set to None (or add your IP). "
                    "Also enable the Places API under APIs & Services."
                )
            else:
                msg += f" ⚠ Places API: {places_error}"
        set_job(job_id, {
            "status": "done",
            "progress": 100,
            "counts": {
                "new_saved": 0,
                "skipped_duplicates": pre_skipped,
                "skipped_already_contacted": 0,
                "skipped_do_not_contact": 0,
                "skipped_no_email": 0,
                "filtered_out": 0,
                **source_counts,
            },
            "message": msg,
        })
        return

    progress(
        15,
        f"Found {len(work)} new candidate sites "
        f"({pre_skipped} already in DB, skipped). Fetching and analysing…",
    )

    kw_lower = [k.lower() for k in keywords]
    stats = {
        "new_saved": 0,
        "skipped_duplicates": pre_skipped,
        "skipped_already_contacted": 0,
        "skipped_do_not_contact": 0,
        "skipped_no_email": 0,
        "filtered_out": 0,
        "filtered_location": 0,
    }

    for i, item in enumerate(work):
        # Hard cap — stop once we've saved enough new agencies.
        if stats["new_saved"] >= max_results:
            progress(95, f"Reached cap of {max_results} agencies — stopping early.")
            break

        pct = 15 + int(80 * (i + 1) / max(len(work), 1))
        progress(pct, f"[{i+1}/{len(work)}] Checking {item.get('website', '')[:55]}…")

        # Final guard: domain may resolve to a known one after normalisation
        d = domain_from_url(item.get("website", ""))
        if d and d in known_domains:
            stats["skipped_duplicates"] += 1
            continue

        html = await _fetch_page(item.get("website", ""))
        if not html:
            stats["filtered_out"] += 1
            continue

        name = item["name"] or _extract_name(html, _domain(item["website"]))
        if _is_blocked_page_name(name):
            stats["filtered_out"] += 1
            continue

        # Location filter — must mention one of the selected locations.
        # Places-sourced items already carry a trusted matched_location; skip
        # the HTML check for them (their homepage may not name the city).
        matched_location: str | None = item.get("matched_location")
        if locations and not matched_location:
            matched_location = _matches_location(html, locations)
            if not matched_location:
                stats["filtered_location"] += 1
                continue

        detected = _detect_stack(html)
        stack_lower = [s.lower() for s in detected]
        html_lower = html.lower()

        # Must match at least one selected keyword (in stack or raw text)
        if not any(k in stack_lower or k in html_lower for k in kw_lower):
            stats["filtered_out"] += 1
            continue

        email = _extract_email(html)
        domain = _domain(item["website"])

        classification = classify_company_candidate(
            db,
            place_id=item.get("place_id", ""),
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

        db.add(Company(
            name=name,
            address=item.get("address") or None,
            phone=item.get("phone") or None,
            website=item["website"],
            email=email,
            company_type="agency",
            source=item.get("source", "scraper"),
            stack_keywords=json.dumps(detected),
            place_id=item.get("place_id") or None,
            category=matched_location,  # store the matched location label
            created_at=datetime.utcnow(),
        ))
        if domain:
            known_domains.add(domain)
        stats["new_saved"] += 1

    db.commit()
    stats.update(source_counts)
    set_job(job_id, {
        "status": "done",
        "progress": 100,
        "counts": stats,
        "message": (
            f"Done — new saved: {stats['new_saved']} (cap {max_results}) · "
            f"skipped duplicates: {stats['skipped_duplicates']} · "
            f"skipped already contacted: {stats['skipped_already_contacted']} · "
            f"skipped do-not-contact: {stats['skipped_do_not_contact']} · "
            f"location-filtered: {stats['filtered_location']} · "
            f"keyword-filtered/no-fetch: {stats['filtered_out']} · "
            f"sources Places={source_counts['places_raw']}/DDG={source_counts['ddg_raw']}/Clutch={source_counts['clutch_raw']}/TB={source_counts['techbehemoths_raw']}."
        ),
    })
