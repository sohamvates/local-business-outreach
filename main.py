import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from database import init_db
from routers import settings, scraper, ai_engine, review_queue, email_sender, crm, system_control, setup

STATIC_DIR = Path(__file__).parent / "static"
INDEX_PATH = STATIC_DIR / "index.html"

# Match <script src="/static/js/foo.js"> and <link href="/static/css/foo.css">
_ASSET_RE = re.compile(r'(src|href)="(/static/[^"?#]+\.(?:js|css))"')


def _render_index_with_cache_busting() -> str:
    """
    Read index.html and append ?v=<mtime> to every /static/*.js or *.css URL.
    The mtime stays stable while the file is unchanged, so unchanged files
    stay cached; any file edit automatically busts the cache.
    """
    html = INDEX_PATH.read_text(encoding="utf-8")

    def _replace(match: re.Match) -> str:
        attr, url = match.group(1), match.group(2)
        # url starts with /static/...; map to filesystem path
        rel = url[len("/static/"):]
        fs_path = STATIC_DIR / rel
        try:
            mtime = int(fs_path.stat().st_mtime)
        except OSError:
            return match.group(0)
        return f'{attr}="{url}?v={mtime}"'

    return _ASSET_RE.sub(_replace, html)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


# Silabs — Sacred Intelligence Labs — https://sacredintelligencelabs.com.au
app = FastAPI(
    title="Nearletter",
    description="Local business outreach. Find businesses, review every email, then send it yourself.",
    version="1.0.0",
    lifespan=lifespan,
)

# ─── Routers ──────────────────────────────────────────────────────────────────
app.include_router(settings.router)
app.include_router(scraper.router)
app.include_router(ai_engine.router)
app.include_router(review_queue.router)
app.include_router(email_sender.router)
app.include_router(crm.router)
app.include_router(system_control.router)
app.include_router(setup.router)

# ─── Static files ─────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=str(STATIC_DIR.resolve())), name="static")


@app.get("/")
def serve_index():
    return HTMLResponse(_render_index_with_cache_busting())


@app.get("/{full_path:path}")
def catch_all(full_path: str):
    """Serve index.html for all non-API routes (SPA routing)."""
    return HTMLResponse(_render_index_with_cache_busting())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
