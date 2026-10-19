import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")


def resolve_database_url(url, project_root):
    """Keep a relative SQLite file inside the project, whatever the working directory is."""
    if url in {"sqlite://", "sqlite:///:memory:"} or not url.startswith("sqlite:///"):
        return url
    if url.startswith("sqlite:////"):
        return url
    raw = url[len("sqlite:///"):]
    path = Path(raw)
    if path.is_absolute():
        return "sqlite:///" + path.as_posix()
    absolute = (Path(project_root) / path).resolve()
    return "sqlite:///" + absolute.as_posix()


DATABASE_URL = resolve_database_url(
    os.getenv("DATABASE_URL", "sqlite:///./outreach.db"),
    PROJECT_ROOT,
)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Required for SQLite + FastAPI threading
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from models import Company, Email, OutreachRecord, DoNotContact  # noqa: F401
    Base.metadata.create_all(bind=engine)
