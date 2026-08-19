from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import get_settings

settings = get_settings()


def normalize_database_url(url: str) -> str:
    """Ensure SQLAlchemy uses psycopg v3 for PostgreSQL URLs.

    Railway exposes DATABASE_URL as `postgresql://...`. Without an explicit
    driver SQLAlchemy defaults to the psycopg2 dialect, but this project ships
    `psycopg[binary]` (psycopg v3). Rewriting the scheme keeps the Railway
    variable unchanged while selecting the installed driver correctly.
    """
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    return url


database_url = normalize_database_url(settings.database_url)

connect_args = {}
if database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    database_url,
    pool_pre_ping=True,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
