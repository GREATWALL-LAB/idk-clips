"""Aggregates versioned routers. Mounted at ``/api`` by ``app.main``."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    account,
    agent,
    auth,
    clips,
    config,
    dashboard,
    health,
    jobs,
    meta,
    projects,
    settings,
    system,
    workers,
)

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(health.router)
v1_router.include_router(meta.router)
v1_router.include_router(system.router)
v1_router.include_router(config.router)
v1_router.include_router(auth.router)
v1_router.include_router(dashboard.router)
v1_router.include_router(projects.router)
v1_router.include_router(clips.router)
v1_router.include_router(jobs.router)
v1_router.include_router(settings.router)
v1_router.include_router(account.router)
v1_router.include_router(workers.router)
v1_router.include_router(agent.router)

api_router = APIRouter()
api_router.include_router(v1_router)
