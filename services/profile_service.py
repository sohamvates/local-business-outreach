"""Local workspace profile.

Secrets stay in .env. This file stores the answers from the first-run assistant:
who the person is, where they search, and which mailbox route to use.
An existing installation that already has a mailbox password keeps its current
behaviour until a profile is completed.
"""
import json
import os
from pathlib import Path

import httpx

from services.settings_service import get_raw, save_settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROFILE = PROJECT_ROOT / "profile.json"
FIND_PLACE_URL = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
PLACE_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
AUTOCOMPLETE_URL = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
AUDIENCES = {"clients", "agencies", "both"}
CITY_TYPES = {
    "locality",
    "postal_town",
    "administrative_area_level_1",
    "administrative_area_level_2",
    "administrative_area_level_3",
    "sublocality",
    "neighborhood",
}


def profile_path() -> Path:
    override = (os.getenv("OUTREACH_PROFILE_PATH") or "").strip()
    return Path(override) if override else DEFAULT_PROFILE


def load_profile() -> dict:
    path = profile_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_profile(data: dict) -> None:
    path = profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _completed(profile: dict | None = None) -> dict | None:
    profile = load_profile() if profile is None else profile
    if profile.get("completed") is True:
        return profile
    return None


def legacy_install() -> bool:
    """True when this machine already has a working mailbox configured."""
    pairs = (
        ("GMAIL_SMTP_USER", "GMAIL_SMTP_PASSWORD"),
        ("CUSTOM_SMTP_USER", "CUSTOM_SMTP_PASSWORD"),
    )
    for user_key, pass_key in pairs:
        user = (get_raw(user_key) or "").strip()
        password = (get_raw(pass_key) or "").strip()
        if user and password and "your_app_password" not in password and not password.startswith("your_"):
            return True
    return False


def mark_setup_started() -> None:
    """Keep the assistant open after it saves a mailbox, until setup finishes.

    An installation that already had a mailbox is left alone.
    """
    profile = load_profile()
    if profile.get("completed") is True or profile.get("setup_in_progress") is True:
        return
    if legacy_install():
        return
    save_profile({"version": 1, "completed": False, "setup_in_progress": True})


def needs_setup() -> bool:
    profile = load_profile()
    if profile.get("completed") is True:
        return False
    if profile.get("setup_in_progress") is True:
        return True
    if legacy_install():
        return False
    return True


def profile_location_coords() -> dict | None:
    profile = _completed()
    if not profile:
        return None
    coords = {}
    for city in profile.get("cities") or []:
        name = (city.get("name") or "").strip()
        lat = city.get("lat")
        lng = city.get("lng")
        if name and isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            coords[name] = (float(lat), float(lng))
    return coords or None


def city_record(name: str) -> dict | None:
    profile = _completed()
    if not profile:
        return None
    for city in profile.get("cities") or []:
        if (city.get("name") or "").strip() == name:
            return city
    return None


def profile_niches() -> list[str] | None:
    profile = _completed()
    if not profile:
        return None
    niches = [str(item).strip() for item in profile.get("niches") or [] if str(item).strip()]
    return niches or None


def profile_city_names() -> list[str] | None:
    coords = profile_location_coords()
    if not coords:
        return None
    return list(coords.keys())


def search_place_label() -> str | None:
    profile = _completed()
    if not profile:
        return None
    country = (profile.get("country") or "").strip()
    names = profile_city_names() or []
    if not names:
        return None
    places = ", ".join(names)
    return f"{places}, {country}" if country else places


def client_search_title() -> str | None:
    label = search_place_label()
    if not label:
        return None
    return f"Search businesses in {label}"


def agency_search_title() -> str | None:
    label = search_place_label()
    if not label:
        return None
    return f"Search digital agencies in {label}"


def forced_sending_via() -> str | None:
    profile = _completed()
    if not profile:
        return None
    via = (profile.get("sending_via") or "").strip()
    if via in {"gmail", "custom"}:
        return via
    return None


def profile_identity() -> dict | None:
    profile = _completed()
    if not profile:
        return None
    identity = profile.get("identity") or {}
    name = (identity.get("name") or "").strip()
    company = (identity.get("company") or "").strip() or name
    role = (identity.get("role") or "").strip()
    email = (identity.get("email") or "").strip()
    if not email:
        return None
    country = (profile.get("country") or "").strip()
    audience = profile.get("audience") or "clients"
    audience_label = {
        "clients": "local businesses",
        "agencies": "agencies",
        "both": "local businesses and agencies",
    }.get(audience, "local businesses")
    who = f"{company} — {role}" if role else company
    where = f" in {country}" if country else ""
    return {
        "from_name": (identity.get("from_name") or "").strip() or company or name,
        "from_email": email,
        "sender_name": name or company,
        "sender_role": role,
        "sender_company": company,
        "sender_email": email,
        "signature": (identity.get("signature") or "").strip(),
        "value_prop": f"{who}. Outreach to {audience_label}{where}.",
        "tone": "personal outreach written for the sender's own business",
    }


def public_status() -> dict:
    profile = _completed() or {}
    identity = profile.get("identity") or {}
    return {
        "needs_setup": needs_setup(),
        "has_profile": bool(profile),
        "country": profile.get("country") if profile else None,
        "country_code": profile.get("country_code") if profile else None,
        "cities": [
            {
                "name": city.get("name") or "",
                "state": city.get("state") or "",
                "formatted_address": city.get("formatted_address") or "",
            }
            for city in (profile.get("cities") or [])
        ] if profile else [],
        "brand_name": (identity.get("company") or identity.get("name") or None) if profile else None,
        "client_search_title": client_search_title(),
        "agency_search_title": agency_search_title(),
        "audience": profile.get("audience") if profile else None,
    }


def _safe_message(message: str, secret: str) -> str:
    if secret and secret in message:
        return message.replace(secret, "[key]")
    return message


def _places_url(kind: str) -> str:
    if kind == "find":
        return (os.getenv("OUTREACH_FIND_PLACE_URL") or FIND_PLACE_URL).strip()
    if kind == "autocomplete":
        return (os.getenv("OUTREACH_AUTOCOMPLETE_URL") or AUTOCOMPLETE_URL).strip()
    return (os.getenv("OUTREACH_PLACE_DETAILS_URL") or PLACE_DETAILS_URL).strip()


def _google_json(url: str, params: dict, api_key: str, label: str) -> dict:
    try:
        response = httpx.get(url, params=params, timeout=15)
        data = response.json()
    except Exception as exc:
        raise ValueError(_safe_message(f"Could not look up {label}: {exc}", api_key)) from exc
    if not isinstance(data, dict):
        raise ValueError(f"Could not look up {label}.")
    return data


def _component(components: list, wanted: str) -> dict:
    for component in components:
        if wanted in (component.get("types") or []):
            return component
    return {}


def lookup_place(query: str, api_key: str) -> dict:
    """Resolve one place with Find Place and then Place Details."""
    found = _google_json(
        _places_url("find"),
        {
            "input": query,
            "inputtype": "textquery",
            "fields": "place_id,name",
            "key": api_key,
        },
        api_key,
        query,
    )
    status = found.get("status", "UNKNOWN")
    if status != "OK" or not found.get("candidates"):
        detail = found.get("error_message") or status
        raise ValueError(_safe_message(f"Google could not find {query}: {detail}", api_key))
    place_id = (found["candidates"][0] or {}).get("place_id") or ""
    if not place_id:
        raise ValueError(f"Google could not find {query}.")

    details = _google_json(
        _places_url("details"),
        {
            "place_id": place_id,
            "fields": "name,formatted_address,geometry,type,address_component",
            "key": api_key,
        },
        api_key,
        query,
    )
    if details.get("status") != "OK":
        detail = details.get("error_message") or details.get("status", "UNKNOWN")
        raise ValueError(_safe_message(f"Google could not confirm {query}: {detail}", api_key))
    result = details.get("result") or {}
    location = (result.get("geometry") or {}).get("location") or {}
    lat = location.get("lat")
    lng = location.get("lng")
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        raise ValueError(f"Google did not return a location for {query}.")
    components = result.get("address_components") or []
    country = _component(components, "country")
    admin = _component(components, "administrative_area_level_1")
    types = result.get("types") or []
    return {
        "name": result.get("name") or query,
        "formatted_address": result.get("formatted_address") or result.get("name") or query,
        "lat": float(lat),
        "lng": float(lng),
        "types": types,
        "country_name": country.get("long_name") or "",
        "country_code": country.get("short_name") or "",
        "admin_area": admin.get("long_name") or "",
    }


def _place_label(value: str) -> str:
    text = " ".join((value or "").casefold().split())
    for prefix in ("state of ", "province of ", "estado de ", "região de ", "regiao de "):
        if text.startswith(prefix):
            text = text[len(prefix):]
    return text


def suggestion_items(kind: str, predictions: list, state_name: str = "") -> list[dict]:
    """Keep Google suggestions that match the step: a state, or a city inside it."""
    kept = []
    state_label = _place_label(state_name)
    for prediction in predictions or []:
        if not isinstance(prediction, dict):
            continue
        types = set(prediction.get("types") or [])
        formatting = prediction.get("structured_formatting") or {}
        name = (formatting.get("main_text") or prediction.get("description") or "").strip()
        if not name:
            continue
        secondary = (formatting.get("secondary_text") or "").strip()
        if kind == "state":
            if "administrative_area_level_1" not in types:
                continue
        else:
            if "locality" not in types and "postal_town" not in types:
                continue
        kept.append({"name": name, "description": secondary or prediction.get("description") or name})
    if kind == "city" and state_label:
        scoped = [item for item in kept if state_label in _place_label(item["description"])]
        if scoped:
            kept = scoped
    unique = []
    seen = set()
    for item in kept:
        key = item["name"].casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique[:8]


def suggest_places(kind: str, query: str, country_code: str, state_name: str, api_key: str) -> list[dict]:
    """Ask Google for states in a country, or cities in a chosen state."""
    query = " ".join((query or "").split())
    country_code = (country_code or "").strip().upper()
    state_name = " ".join((state_name or "").split())
    if kind not in {"state", "city"}:
        raise ValueError("Choose a state or a city.")
    if len(query) < 2:
        return []
    if len(country_code) != 2:
        raise ValueError("Choose a country first.")
    if not api_key:
        raise ValueError("Save the Google Maps API key before choosing a state or city.")
    typed = query
    data = _google_json(
        _places_url("autocomplete"),
        {
            "input": typed,
            "types": "(regions)" if kind == "state" else "(cities)",
            "components": f"country:{country_code.lower()}",
            "key": api_key,
        },
        api_key,
        typed,
    )
    status = data.get("status", "UNKNOWN")
    if status == "ZERO_RESULTS":
        return []
    if status != "OK":
        detail = data.get("error_message") or status
        raise ValueError(_safe_message(f"Google could not suggest {typed}: {detail}", api_key))
    return suggestion_items(kind, data.get("predictions") or [], state_name)


def resolve_places(country: str, cities: list[str], api_key: str, city_states: list[str] | None = None) -> dict:
    """Confirm the country, then each chosen city inside that country and state."""
    country = " ".join((country or "").split())
    cities = _clean_lines(cities)
    if not country:
        raise ValueError("Enter a country.")
    if not cities:
        raise ValueError("Enter at least one city.")
    if not api_key:
        raise ValueError("Save the Google Maps API key before checking places.")

    country_place = lookup_place(country, api_key)
    if "country" not in country_place["types"] or not country_place["country_code"]:
        raise ValueError(
            f"Google found “{country_place['formatted_address']}”, which is not a country. "
            "Enter the country, then the cities inside it."
        )

    resolved = []
    seen = set()
    city_states = city_states or []
    for index, city in enumerate(cities):
        state = city_states[index] if index < len(city_states) else ""
        state = " ".join((state or "").split())
        query = f"{city}, {state}, {country_place['country_name']}" if state else f"{city}, {country_place['country_name']}"
        hit = lookup_place(query, api_key)
        if hit["country_code"] != country_place["country_code"]:
            raise ValueError(
                f"Google found “{hit['formatted_address']}” for {city}, "
                f"outside {country_place['country_name']}."
            )
        if state and hit["admin_area"] and _place_label(hit["admin_area"]) != _place_label(state):
            raise ValueError(
                f"Google found “{hit['formatted_address']}” for {city}, which is not in {state}."
            )
        if not CITY_TYPES.intersection(hit["types"]):
            raise ValueError(
                f"Google found “{hit['formatted_address']}” for {city}. Enter a city in {country_place['country_name']}."
            )
        key = hit["formatted_address"].lower()
        if key in seen:
            continue
        seen.add(key)
        resolved.append({
            "name": city,
            "state": state,
            "formatted_address": hit["formatted_address"],
            "lat": hit["lat"],
            "lng": hit["lng"],
            "query": query,
        })
    return {
        "country_name": country_place["country_name"],
        "country_code": country_place["country_code"],
        "cities": resolved,
    }


def _clean_lines(values: list[str]) -> list[str]:
    seen = set()
    cleaned = []
    for value in values:
        item = " ".join(str(value).split())
        key = item.lower()
        if item and key not in seen:
            seen.add(key)
            cleaned.append(item)
    return cleaned


def _choices(payload: dict) -> tuple[list[str], list[str]]:
    raw = payload.get("choices") or []
    if raw:
        cities = []
        states = []
        for choice in raw:
            if not isinstance(choice, dict):
                continue
            city = " ".join(str(choice.get("city") or "").split())
            state = " ".join(str(choice.get("state") or "").split())
            if city:
                cities.append(city)
                states.append(state)
        return cities, states
    return _clean_lines(payload.get("cities") or []), []


def update_places(country: str, choices: list[dict], api_key: str) -> dict:
    """Replace the saved country and cities. Identity and mailbox stay as they are."""
    profile = _completed()
    if not profile:
        return {"ok": False, "message": "Finish setup before editing places."}
    cities, states = _choices({"choices": choices})
    if not (country or "").strip() or not cities:
        return {"ok": False, "message": "Choose one country and at least one city."}
    try:
        resolved = resolve_places(country, cities, api_key, states)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}
    profile["country"] = resolved["country_name"]
    profile["country_code"] = resolved["country_code"]
    profile["cities"] = resolved["cities"]
    save_profile(profile)
    return {"ok": True, "message": "Places saved.", "status": public_status()}


def complete_setup(payload: dict) -> dict:
    name = (payload.get("name") or "").strip()
    company = (payload.get("company") or "").strip()
    country = (payload.get("country") or "").strip()
    cities, city_states = _choices(payload)
    niches = _clean_lines(payload.get("niches") or [])
    audience = (payload.get("audience") or "").strip()
    smtp_user = (payload.get("smtp_user") or "").strip()
    smtp_password = payload.get("smtp_password") or ""
    smtp_host = (payload.get("smtp_host") or "").strip()
    smtp_port = str(payload.get("smtp_port") or "587").strip()
    from_name = (payload.get("from_name") or "").strip() or company or name
    claude_key = (payload.get("claude_api_key") or "").strip()
    maps_key = (payload.get("google_maps_api_key") or "").strip()
    signature = (payload.get("signature") or "").strip()
    via = "gmail" if "gmail" in smtp_host.lower() else "custom"

    try:
        daily_limit = int(payload.get("daily_limit") or 25)
    except (TypeError, ValueError):
        daily_limit = 0

    missing = []
    if not name:
        missing.append("your name")
    if not country:
        missing.append("a country")
    if not cities:
        missing.append("at least one city")
    if audience not in AUDIENCES:
        missing.append("who you want to contact")
    if not niches:
        missing.append("at least one niche")
    if not smtp_host or not smtp_user or not smtp_password:
        missing.append("the sending mailbox")
    if not claude_key:
        missing.append("the Claude API key")
    if not maps_key:
        missing.append("the Google Maps API key")
    if daily_limit < 1 or daily_limit > 200:
        missing.append("a daily send limit between 1 and 200")
    if missing:
        return {"ok": False, "message": "Add " + ", ".join(missing) + "."}

    mark_setup_started()

    if not signature:
        signature = "\n".join(
            line for line in (
                name,
                (payload.get("role") or "").strip(),
                company,
                (payload.get("phone") or "").strip(),
                smtp_user,
                (payload.get("website") or "").strip(),
            ) if line
        )
    elif smtp_user and smtp_user.lower() not in signature.lower():
        signature = f"{signature.rstrip()}\n{smtp_user}"

    prefix = "GMAIL" if via == "gmail" else "CUSTOM"
    save_settings({
        f"{prefix}_SMTP_HOST": smtp_host,
        f"{prefix}_SMTP_PORT": smtp_port,
        f"{prefix}_SMTP_USER": smtp_user,
        f"{prefix}_SMTP_PASSWORD": smtp_password,
        f"{prefix}_FROM_NAME": from_name,
        "CLAUDE_API_KEY": claude_key,
        "GOOGLE_MAPS_API_KEY": maps_key,
        "DAILY_SEND_LIMIT": str(daily_limit),
        "DELIVERABILITY_SAFE_MODE": "true",
    })

    try:
        resolved = resolve_places(country, cities, maps_key, city_states)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}

    save_profile({
        "version": 1,
        "completed": True,
        "country": resolved["country_name"],
        "country_code": resolved["country_code"],
        "audience": audience,
        "cities": resolved["cities"],
        "niches": niches,
        "sending_via": via,
        "identity": {
            "name": name,
            "company": company,
            "role": (payload.get("role") or "").strip(),
            "phone": (payload.get("phone") or "").strip(),
            "website": (payload.get("website") or "").strip(),
            "email": smtp_user,
            "from_name": from_name,
            "signature": signature,
        },
    })
    return {"ok": True, "message": "Workspace ready.", "status": public_status()}
