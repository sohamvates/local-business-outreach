"""
Persistent job store service.

Replaces the in-memory _jobs dict with file-based JSON persistence.
Jobs survive server restarts and can be queried after a crash.

Thread-safe via file locking for concurrent background job updates.
"""
import json
import os
import fcntl
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

JOB_STORE_PATH = Path(__file__).parent.parent / ".job_store.json"
JOB_TTL_HOURS = 24  # Jobs auto-expire after 24 hours


def _load_store() -> dict:
    """Load job store from disk, return empty dict if missing/corrupt."""
    if not JOB_STORE_PATH.exists():
        return {}
    try:
        with open(JOB_STORE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_store(store: dict) -> None:
    """Save job store to disk with file locking for thread safety."""
    JOB_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = JOB_STORE_PATH.with_suffix(".json.tmp")

    try:
        # Write to temp file first (atomic write pattern)
        with open(tmp_path, "w", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                json.dump(store, f, indent=2, default=str)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        # Atomic rename
        os.replace(tmp_path, JOB_STORE_PATH)
    except Exception:
        # Clean up temp file on failure
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def _is_expired(job: dict) -> bool:
    """Check if a job has exceeded its TTL."""
    created_at = job.get("created_at")
    if not created_at:
        return False
    try:
        # Handle both datetime objects and ISO strings
        if isinstance(created_at, str):
            created = datetime.fromisoformat(created_at)
        else:
            created = created_at
        return datetime.utcnow() - created > timedelta(hours=JOB_TTL_HOURS)
    except (ValueError, TypeError):
        return False


def get_job(job_id: str) -> Optional[dict]:
    """Get a job by ID, or None if not found/expired."""
    store = _load_store()
    job = store.get(job_id)
    if not job:
        return None

    if _is_expired(job):
        # Clean up expired job
        del store[job_id]
        _save_store(store)
        return None

    return job


def set_job(job_id: str, data: dict) -> None:
    """
    Set or update a job.

    Automatically adds created_at timestamp for TTL tracking.
    """
    store = _load_store()
    job = store.get(job_id, {})
    if "created_at" not in job:
        job["created_at"] = datetime.utcnow()
    job.update(data)
    store[job_id] = job
    _save_store(store)


def delete_job(job_id: str) -> bool:
    """Delete a job. Returns True if it existed."""
    store = _load_store()
    if job_id in store:
        del store[job_id]
        _save_store(store)
        return True
    return False


def list_jobs() -> dict:
    """List all non-expired jobs."""
    store = _load_store()
    # Filter out expired jobs
    active = {jid: job for jid, job in store.items() if not _is_expired(job)}
    # Clean up expired ones
    if len(active) != len(store):
        _save_store(active)
    return active


def cleanup_expired() -> int:
    """Remove all expired jobs. Returns count of removed jobs."""
    store = _load_store()
    original_count = len(store)
    active = {jid: job for jid, job in store.items() if not _is_expired(job)}
    if len(active) < original_count:
        _save_store(active)
    return original_count - len(active)
