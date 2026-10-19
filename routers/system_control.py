import os
import signal
import threading

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from start import restart_command
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db

router = APIRouter(prefix="/api/system", tags=["system"])

_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _require_local(request: Request) -> None:
    client_host = request.client.host if request.client else ""
    if client_host not in _LOCAL_HOSTS:
        raise HTTPException(status_code=403, detail="Local access only.")


@router.get("/status")
def get_system_status(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {
        "ok": True,
        "database_connected": True,
        "restart_command": restart_command(),
    }


def _stop_process() -> None:
    os.kill(os.getpid(), signal.SIGTERM)


@router.post("/stop")
def stop_system(request: Request, background_tasks: BackgroundTasks):
    _require_local(request)
    background_tasks.add_task(threading.Timer(0.5, _stop_process).start)
    return {
        "ok": True,
        "message": "System stop requested. Start it again with %s." % restart_command(),
    }
