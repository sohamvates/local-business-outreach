from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.profile_service import (
    complete_setup,
    mark_setup_started,
    public_status,
    resolve_places,
    suggest_places,
    update_places,
)
from services.settings_service import get_raw

router = APIRouter(prefix="/api/setup", tags=["setup"])


class PlaceChoice(BaseModel):
    city: str = ""
    state: str = ""


class SetupPayload(BaseModel):
    name: str = ""
    company: str = ""
    role: str = ""
    phone: str = ""
    website: str = ""
    signature: str = ""
    country: str = ""
    cities: list[str] = Field(default_factory=list)
    choices: list[PlaceChoice] = Field(default_factory=list)
    audience: str = ""
    niches: list[str] = Field(default_factory=list)
    smtp_host: str = ""
    smtp_port: str = "587"
    smtp_user: str = ""
    smtp_password: str = ""
    from_name: str = ""
    daily_limit: int = 25
    claude_api_key: str = ""
    google_maps_api_key: str = ""


class ResolvePayload(BaseModel):
    country: str = ""
    cities: list[str] = Field(default_factory=list)
    choices: list[PlaceChoice] = Field(default_factory=list)


class SuggestPayload(BaseModel):
    kind: str = ""
    query: str = ""
    country_code: str = ""
    state_name: str = ""


class UpdatePlacesPayload(BaseModel):
    country: str = ""
    choices: list[PlaceChoice] = Field(default_factory=list)


@router.get("/status")
def setup_status():
    return public_status()


@router.post("/progress")
def setup_progress():
    mark_setup_started()
    return {"ok": True}


def _choice_lists(payload: ResolvePayload):
    if payload.choices:
        cities = []
        states = []
        for choice in payload.choices:
            city = " ".join(choice.city.split())
            if city:
                cities.append(city)
                states.append(" ".join(choice.state.split()))
        return cities, states
    return payload.cities, []


@router.post("/suggest-places")
def suggest_setup_places(payload: SuggestPayload):
    api_key = (get_raw("GOOGLE_MAPS_API_KEY") or "").strip()
    try:
        items = suggest_places(payload.kind, payload.query, payload.country_code, payload.state_name, api_key)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}
    return {"ok": True, "items": items}


@router.post("/resolve-places")
def resolve_setup_places(payload: ResolvePayload):
    api_key = (get_raw("GOOGLE_MAPS_API_KEY") or "").strip()
    if not api_key:
        return {"ok": False, "message": "Save the Google Maps API key before checking places."}
    cities, states = _choice_lists(payload)
    try:
        found = resolve_places(payload.country, cities, api_key, states)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}
    return {"ok": True, **found}


@router.post("/places")
def save_places(payload: UpdatePlacesPayload):
    api_key = (get_raw("GOOGLE_MAPS_API_KEY") or "").strip()
    if not api_key:
        return {"ok": False, "message": "Save the Google Maps API key before editing places."}
    return update_places(payload.country, [choice.model_dump() for choice in payload.choices], api_key)


@router.post("")
def finish_setup(payload: SetupPayload):
    return complete_setup(payload.model_dump())
