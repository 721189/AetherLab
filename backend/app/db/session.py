"""Database engine and session factory.

Supports both PostgreSQL (production) and SQLite (local development).

PostgreSQL requires no special engine options. SQLite needs a couple of tuning
flags so that the same in-process engine is safe when FastAPI hands sync
requests to its threadpool (``check_same_thread=False``), and so an in-memory
database keeps a single shared connection alive instead of creating a fresh
empty database per checkout (``StaticPool``).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings


def build_engine(url: str):
    """Create a SQLAlchemy engine, applying SQLite-specific options when needed."""
    if url.startswith("sqlite"):
        # SQLite connections must not be shared across threads by default;
        # FastAPI resolves sync routes/dependencies on a threadpool.
        connect_args = {"check_same_thread": False}

        # In-memory databases (``sqlite://`` / ``:memory:``) need a single
        # persistent connection — otherwise each checked-out connection would
        # point at a brand-new, empty database.
        if ":memory:" in url or url in ("sqlite://", "sqlite+pysqlite://"):
            return create_engine(
                url,
                connect_args=connect_args,
                poolclass=StaticPool,
            )

        # File-backed SQLite (e.g. sqlite:///./aetherlab.db).
        return create_engine(url, connect_args=connect_args, pool_pre_ping=True)

    # PostgreSQL and other server-backed engines.
    return create_engine(url, pool_pre_ping=True)


engine = build_engine(settings.DATABASE_URL)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)