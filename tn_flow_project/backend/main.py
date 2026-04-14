"""
TN-Flow FastAPI Application — main.py
======================================
Entry point for the TN-Flow Layout Engine web API.

Startup behaviour:
  1. Creates all database tables (idempotent — safe to call on every start).
  2. Seeds the database with TNCDBR 2019 rules and Vastu logic if empty
     (seed_all() is idempotent; it validates row counts before inserting).
  3. Mounts the API router under /api (all routes are prefixed there).

Run locally (from project root /app/tn_flow_project/):
    uvicorn backend.main:app --host 0.0.0.0 --port 8001 --reload

Interactive docs:
    http://localhost:8001/docs       ← Swagger UI
    http://localhost:8001/redoc      ← ReDoc

Environment variables:
    DATABASE_URL  — SQLAlchemy DB URL (default: sqlite:///./tn_flow.db)
                    Set to postgresql://... for production.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database.db import engine
from backend.database.models import Base
from backend.api.routes import router


# ── Lifespan (replaces deprecated @app.on_event("startup")) ──────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.

    Runs on startup:
        - Creates all ORM-mapped tables if they don't exist (DDL is idempotent).
        - Seeds TNCDBR 2019 PlotEligibilityRules and VastuGridLogic if empty.

    Yields control to FastAPI while the server is live, then cleans up on shutdown.
    """
    # ── Startup ───────────────────────────────────────────────────────────
    # Create tables (no-op if already present)
    Base.metadata.create_all(bind=engine)

    # Seed rules + Vastu data (idempotent — validates row counts first)
    try:
        from backend.database.seed_rules_vastu import seed_all
        seed_all()
    except Exception as exc:  # pragma: no cover
        # Seed failure should not crash the API — log and continue
        import logging
        logging.getLogger(__name__).warning(
            "Database seed failed (non-fatal): %s", exc
        )

    yield  # Hand control to FastAPI

    # ── Shutdown (clean-up hooks go here if needed) ───────────────────────


# ── FastAPI Application Instance ─────────────────────────────────────────────

app = FastAPI(
    title="TN-Flow Layout Engine",
    description=(
        "TNCDBR 2019 compliant residential floor plan generator for Tamil Nadu.\n\n"
        "The engine enforces:\n"
        "- **TNCDBR 2019** setback and FSI regulations per authority (CMDA / DTCP)\n"
        "- **NBC 2016** minimum carpet area requirements per room type\n"
        "- **Vastu Purusha Mandala** 3×3 compass zone routing for room placement\n\n"
        "Pipeline: Validation Gate → Vastu Router → Spatial Allocator → "
        "Geometry Engine → CAD SVG Renderer"
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ── CORS Middleware ───────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten in production (list specific origins)
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# ── API Router ────────────────────────────────────────────────────────────────

app.include_router(router)


# ── Health Check ─────────────────────────────────────────────────────────────

@app.get("/api/health", tags=["system"], summary="API health check")
def health() -> dict:
    """
    Returns a simple liveness probe.
    Useful for container orchestration (Kubernetes readiness checks, etc.).
    """
    return {"status": "ok", "service": "tn-flow-engine", "version": "1.0.0"}
