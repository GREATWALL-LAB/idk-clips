"""Public facts the web app needs before anyone signs in (no authentication, no secrets)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel

from app import __version__
from app.api.deps import DbSession, SettingsDep
from app.services.auth import user_count

router = APIRouter(tags=["system"])


class MetaOut(BaseModel):
    name: str
    version: str
    mode: Literal["local", "server", "hybrid"]
    accounts: bool
    registration_open: bool
    has_users: bool
    processing: Literal["this_computer", "this_server", "your_worker"]
    youtube_reference_enabled: bool
    url_import_enabled: bool


@router.get("/meta", response_model=MetaOut, summary="How this IDK Clips instance runs")
def meta(db: DbSession, settings: SettingsDep, response: Response) -> MetaOut:
    # The same for every visitor and rarely changes: browsers and CDNs may reuse it briefly.
    response.headers["Cache-Control"] = "public, max-age=60"
    has_users = True if not settings.accounts_enabled else user_count(db) > 0
    processing = {"local": "this_computer", "server": "this_server", "hybrid": "your_worker"}
    return MetaOut(
        name=settings.app_name,
        version=__version__,
        mode=settings.mode,
        accounts=settings.accounts_enabled,
        registration_open=settings.accounts_enabled and settings.registration_available,
        has_users=has_users,
        processing=processing[settings.mode],  # type: ignore[arg-type]
        youtube_reference_enabled=settings.youtube_lookup_enabled,
        url_import_enabled=settings.url_import_enabled,
    )
