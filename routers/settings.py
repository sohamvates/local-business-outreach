from fastapi import APIRouter
from pydantic import BaseModel
from services.settings_service import (
    get_settings,
    save_settings,
    get_raw,
    test_smtp,
    test_claude,
    test_google_maps,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsPayload(BaseModel):
    GMAIL_SMTP_HOST: str = ""
    GMAIL_SMTP_PORT: str = ""
    GMAIL_SMTP_USER: str = ""
    GMAIL_SMTP_PASSWORD: str = ""
    GMAIL_FROM_NAME: str = ""
    CUSTOM_SMTP_HOST: str = ""
    CUSTOM_SMTP_PORT: str = ""
    CUSTOM_SMTP_USER: str = ""
    CUSTOM_SMTP_PASSWORD: str = ""
    CUSTOM_FROM_NAME: str = ""
    CLAUDE_API_KEY: str = ""
    GOOGLE_MAPS_API_KEY: str = ""
    GOOGLE_SHEETS_ID: str = ""
    CLIENTS_MAX_RESULTS: str = ""
    DELIVERABILITY_SAFE_MODE: str = ""
    DAILY_SEND_LIMIT: str = ""


@router.get("")
def read_settings():
    return get_settings(mask_sensitive=True)


@router.post("")
def write_settings(payload: SettingsPayload):
    save_settings(payload.model_dump())
    return {"ok": True, "message": "Settings saved."}


@router.post("/test/gmail-smtp")
def test_gmail_smtp():
    host = get_raw("GMAIL_SMTP_HOST")
    port = int(get_raw("GMAIL_SMTP_PORT") or 587)
    user = get_raw("GMAIL_SMTP_USER")
    password = get_raw("GMAIL_SMTP_PASSWORD")
    return test_smtp(host, port, user, password)


@router.post("/test/custom-smtp")
def test_custom_smtp():
    host = get_raw("CUSTOM_SMTP_HOST")
    port = int(get_raw("CUSTOM_SMTP_PORT") or 587)
    user = get_raw("CUSTOM_SMTP_USER")
    password = get_raw("CUSTOM_SMTP_PASSWORD")
    return test_smtp(host, port, user, password)


@router.post("/test/claude")
def test_claude_key():
    api_key = get_raw("CLAUDE_API_KEY")
    if not api_key:
        return {"ok": False, "message": "No Claude API key configured."}
    return test_claude(api_key)


@router.post("/test/google-maps")
def test_maps_key():
    api_key = get_raw("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return {"ok": False, "message": "No Google Maps API key configured."}
    return test_google_maps(api_key)
