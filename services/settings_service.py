"""
Settings service — reads/writes to .env file.
Keeps .env as the single source of truth for all API keys and SMTP config,
so secrets never touch the database.
"""
import os
import smtplib
import ssl
from pathlib import Path
from dotenv import dotenv_values, set_key, load_dotenv

def env_path() -> Path:
    override = (os.getenv("OUTREACH_ENV_FILE") or "").strip()
    return Path(override) if override else Path(__file__).parent.parent / ".env"


ENV_FILE = Path(__file__).parent.parent / ".env"

# All managed keys with their defaults
SETTINGS_SCHEMA: dict[str, str] = {
    "GMAIL_SMTP_HOST": "smtp.gmail.com",
    "GMAIL_SMTP_PORT": "587",
    "GMAIL_SMTP_USER": "",
    "GMAIL_SMTP_PASSWORD": "",
    "GMAIL_FROM_NAME": "",               # Display name for Gmail From header
    "CUSTOM_SMTP_HOST": "",
    "CUSTOM_SMTP_PORT": "587",
    "CUSTOM_SMTP_USER": "",
    "CUSTOM_SMTP_PASSWORD": "",
    "CUSTOM_FROM_NAME": "",          # Display name for custom SMTP From header
    "CLAUDE_API_KEY": "",
    "GOOGLE_MAPS_API_KEY": "",
    "GOOGLE_SHEETS_ID": "",
    "CLIENTS_MAX_RESULTS": "20",   # Max clients to save per search job
    "DELIVERABILITY_SAFE_MODE": "true",
    "DAILY_SEND_LIMIT": "25",      # Sends allowed per calendar day; 0 disables the cap
}

# Keys whose values should never be returned to the client in plain text
SENSITIVE_KEYS = {"GMAIL_SMTP_PASSWORD", "CUSTOM_SMTP_PASSWORD", "CLAUDE_API_KEY", "GOOGLE_MAPS_API_KEY"}


def get_settings(mask_sensitive: bool = True) -> dict:
    """Return all settings, optionally masking sensitive values."""
    env_values = dotenv_values(env_path())
    result = {}
    for key, default in SETTINGS_SCHEMA.items():
        raw = env_values.get(key, default)
        if mask_sensitive and key in SENSITIVE_KEYS and raw:
            result[key] = "••••••••"
        else:
            result[key] = raw or ""
    return result


def save_settings(data: dict) -> None:
    """
    Persist settings to .env.
    Only updates keys present in SETTINGS_SCHEMA.
    Skips masked placeholder values so we don't overwrite real secrets.
    """
    path = env_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    env_file_str = str(path)
    for raw_key, value in data.items():
        key = raw_key.upper()
        if key not in SETTINGS_SCHEMA:
            continue
        if value == "••••••••":
            continue  # UI sent back a masked placeholder — leave existing value intact
        set_key(env_file_str, key, value, quote_mode="never")

    # Reload into process environment so new values take effect immediately
    load_dotenv(env_path(), override=True)


def get_raw(key: str) -> str:
    """Get a single unmasked value directly from the active .env file."""
    env_values = dotenv_values(env_path())
    value = env_values.get(key.upper())
    if value:
        return value
    # A dedicated env file, used by tests and a second local install, must not
    # inherit secrets that happen to be in the process environment.
    if (os.getenv("OUTREACH_ENV_FILE") or "").strip():
        return ""
    return os.getenv(key.upper(), "") or ""


# ─── Connection testers ────────────────────────────────────────────────────────

def test_smtp(host: str, port: int, user: str, password: str) -> dict:
    """Try an authenticated STARTTLS connection; return status dict."""
    override = (os.getenv("OUTREACH_SMTP_TEST_URL") or "").strip()
    if override:
        import httpx
        try:
            response = httpx.post(override, json={"host": host, "user": user}, timeout=5)
            data = response.json()
        except Exception as exc:
            return {"ok": False, "message": str(exc)}
        if data.get("ok"):
            return {"ok": True, "message": f"Connected to {host}:{port} successfully."}
        return {"ok": False, "message": data.get("message") or "Mailbox connection failed."}
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
            if user and password:
                smtp.login(user, password)
        return {"ok": True, "message": f"Connected to {host}:{port} successfully."}
    except smtplib.SMTPAuthenticationError:
        return {"ok": False, "message": "Authentication failed — check username and password."}
    except Exception as e:
        return {"ok": False, "message": str(e)}


def test_claude(api_key: str) -> dict:
    """Validate a Claude API key with a minimal ping."""
    override = (os.getenv("OUTREACH_CLAUDE_TEST_URL") or "").strip()
    if override:
        import httpx
        try:
            response = httpx.post(override, json={"ping": "claude"}, timeout=5)
            data = response.json()
        except Exception as exc:
            message = str(exc)
            if api_key:
                message = message.replace(api_key, "[key]")
            return {"ok": False, "message": message}
        if data.get("ok"):
            return {"ok": True, "message": "Claude API key is valid."}
        message = data.get("message") or "Claude key was rejected."
        if api_key:
            message = message.replace(api_key, "[key]")
        return {"ok": False, "message": message}
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=5,
            messages=[{"role": "user", "content": "hi"}],
        )
        return {"ok": True, "message": "Claude API key is valid."}
    except Exception as e:
        return {"ok": False, "message": str(e)}


def test_google_maps(api_key: str) -> dict:
    """Ping the Maps Places API with a minimal request."""
    import httpx
    url = (
        os.getenv("OUTREACH_FIND_PLACE_URL")
        or "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
    ).strip()
    params = {"input": "Sydney", "inputtype": "textquery", "key": api_key}
    try:
        r = httpx.get(url, params=params, timeout=10)
        data = r.json()
        if data.get("status") in ("OK", "ZERO_RESULTS"):
            return {"ok": True, "message": "Google Maps API key is valid."}
        detail = f"{data.get('status')} — {data.get('error_message', '')}"
        if api_key:
            detail = detail.replace(api_key, "[key]")
        return {"ok": False, "message": f"API error: {detail}"}
    except Exception as e:
        message = str(e)
        if api_key:
            message = message.replace(api_key, "[key]")
        return {"ok": False, "message": message}
