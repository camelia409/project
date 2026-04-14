"""
TN-Flow Database Connection & Session Factory
=============================================
Configures SQLAlchemy for SQLite (dev) or PostgreSQL (prod).
Set the DATABASE_URL environment variable to switch engines.

Usage:
    from database.db import SessionLocal, engine
    from database.models import Base
    Base.metadata.create_all(bind=engine)   # run once on startup
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Default: SQLite file in the project root for rapid prototyping.
# Override with:  DATABASE_URL=postgresql://user:pass@localhost/tnflow
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./tn_flow.db"
)

# connect_args is SQLite-specific; ignored by PostgreSQL.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=False,           # set True to log every SQL statement during debug
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency — yields a DB session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
