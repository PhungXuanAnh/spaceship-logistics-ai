"""FastAPI entrypoint."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_ask, routes_ask_v2, routes_auth, routes_health, routes_kpis
from app.db.models import Base  # noqa: F401 — register models
from app.db.session import engine
from app.settings import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Auto-create tables on startup (Alembic-free path for SQLite/dev convenience)
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Spaceship Logistics Analytics API",
    version="0.1.0",
    description="AI-powered logistics analytics dashboard backend.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_health.router)
app.include_router(routes_auth.router)
app.include_router(routes_kpis.router)
app.include_router(routes_ask.router)
app.include_router(routes_ask_v2.router)


@app.get("/")
def root():
    return {"name": "spaceship-logistics-ai", "docs": "/docs"}
