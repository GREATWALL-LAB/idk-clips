"""Paired workers (hybrid mode): pairing codes, credentials, job leases, transfer tokens.

Security model in short:

- A signed-in user creates a **pairing code**: 8 characters, single use, valid for a
  few minutes. Only its hash is stored. Typing it into the worker on their own
  computer links that worker to their account.
- The worker receives a **bearer token** (256 random bits) exactly once. The server
  keeps a SHA-256 hash, so a database leak does not expose usable credentials.
  Revoking the worker makes the token useless immediately.
- A worker can only claim jobs that belong to its owner, and every result it reports
  is validated and limited to that job's own project (``app.jobs.events``).
- The owner's browser talks to the worker's local bridge with short-lived
  **transfer tokens** that the worker checks with the server before trusting them.
"""

from __future__ import annotations

import logging
import secrets
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, UnprocessableError
from app.core.security import hash_token
from app.db.base import utcnow
from app.db.models import Job, PairingCode, Project, TransferToken, Worker
from app.db.session import Database
from app.jobs.lifecycle import finish_job
from app.jobs.specs import build_spec
from app.services.storage import LocalStorage
from openclip_processing.errors import ProcessingError

logger = logging.getLogger("app.workers")

#: No 0/O, 1/I/L: the code is read from a screen and typed by a person.
PAIRING_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
PAIRING_LENGTH = 8
MAX_ACTIVE_CODES = 5
WORKER_TOKEN_PREFIX = "ocw_"  # noqa: S105 - a public prefix, not a secret
TRANSFER_TOKEN_PREFIX = "oct_"  # noqa: S105
WORKER_GONE = (
    "Your worker stopped responding while it was processing. Check that it is running and "
    "connected, then try again."
)


# ------------------------------------------------------------------ pairing
def normalize_code(raw: str) -> str:
    return "".join(ch for ch in raw.upper() if ch.isalnum())


def format_code(code: str) -> str:
    return f"{code[:4]}-{code[4:]}"


def create_pairing_code(db: Session, settings: Settings, owner_id: str) -> tuple[str, PairingCode]:
    now = utcnow()
    db.execute(delete(PairingCode).where(PairingCode.expires_at < now))
    active_workers = db.scalar(
        select(func.count()).where(Worker.owner_id == owner_id, Worker.status == "active")
    )
    if int(active_workers or 0) >= settings.max_workers_per_user:
        raise ConflictError(
            f"You already have {settings.max_workers_per_user} connected workers. Remove one first.",
            code="too_many_workers",
        )
    pending = db.scalar(
        select(func.count()).where(PairingCode.owner_id == owner_id, PairingCode.used_at.is_(None))
    )
    if int(pending or 0) >= MAX_ACTIVE_CODES:
        raise ConflictError(
            "You have several unused pairing codes. Use one of them or wait for them to expire.",
            code="too_many_codes",
        )
    code = "".join(secrets.choice(PAIRING_ALPHABET) for _ in range(PAIRING_LENGTH))
    row = PairingCode(
        owner_id=owner_id,
        code_hash=hash_token(code),
        expires_at=now + timedelta(minutes=settings.pairing_code_minutes),
    )
    db.add(row)
    db.commit()
    return format_code(code), row


def pair_worker(
    db: Session,
    settings: Settings,
    *,
    code: str,
    name: str,
    platform: str,
    app_version: str,
    bridge_port: int,
    capabilities: dict[str, Any],
) -> tuple[Worker, str]:
    """Exchange a pairing code for worker credentials. The code works exactly once."""
    normalized = normalize_code(code)
    invalid = UnprocessableError(
        "This pairing code is not valid. Codes expire after a few minutes and work only once; "
        "create a new one in the dashboard.",
        code="invalid_pairing_code",
    )
    if len(normalized) != PAIRING_LENGTH:
        raise invalid
    now = utcnow()
    # Mark the code as used in one statement so two workers can never share it.
    claimed = db.execute(
        update(PairingCode)
        .where(
            PairingCode.code_hash == hash_token(normalized),
            PairingCode.used_at.is_(None),
            PairingCode.expires_at > now,
        )
        .values(used_at=now)
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise invalid
    row = db.scalar(select(PairingCode).where(PairingCode.code_hash == hash_token(normalized)))
    if row is None:  # pragma: no cover - the row was just updated
        db.rollback()
        raise invalid
    token = WORKER_TOKEN_PREFIX + secrets.token_urlsafe(32)
    worker = Worker(
        owner_id=row.owner_id,
        name=" ".join(name.split())[:80] or "My computer",
        token_hash=hash_token(token),
        platform=platform[:40],
        app_version=app_version[:20],
        bridge_port=bridge_port,
        capabilities=capabilities,
        last_seen_at=now,
    )
    db.add(worker)
    db.commit()
    logger.info("Worker paired", extra={"worker_id": worker.id})
    return worker, token


def worker_for_token(db: Session, token: str) -> Worker | None:
    if not token or not token.startswith(WORKER_TOKEN_PREFIX) or len(token) > 200:
        return None
    worker = db.scalar(select(Worker).where(Worker.token_hash == hash_token(token)))
    if worker is None or worker.status != "active":
        return None
    return worker


def touch_worker(db: Session, worker: Worker, min_interval: float = 5.0) -> None:
    now = utcnow()
    if worker.last_seen_at is None or (now - worker.last_seen_at).total_seconds() >= min_interval:
        worker.last_seen_at = now
        db.commit()


def is_online(worker: Worker, settings: Settings) -> bool:
    if worker.status != "active" or worker.last_seen_at is None:
        return False
    return (utcnow() - worker.last_seen_at).total_seconds() <= settings.worker_offline_seconds


def get_owned_worker(db: Session, owner_id: str, worker_id: str) -> Worker:
    worker = db.scalar(
        select(Worker).where(
            Worker.id == worker_id, Worker.owner_id == owner_id, Worker.status == "active"
        )
    )
    if worker is None:
        raise NotFoundError("Worker not found.")
    return worker


def revoke_worker(db: Session, database: Database, storage: LocalStorage, worker: Worker) -> None:
    """Disconnect a worker: its token stops working and its unfinished jobs are settled."""
    worker.status = "revoked"
    worker.revoked_at = utcnow()
    worker.token_hash = hash_token(secrets.token_urlsafe(32))  # the old token can never match again
    db.execute(delete(TransferToken).where(TransferToken.worker_id == worker.id))
    active = db.scalars(
        select(Job.id).where(Job.worker_id == worker.id, Job.status.in_(("queued", "running")))
    ).all()
    db.commit()
    for job_id in active:
        finish_job(
            database,
            storage,
            job_id,
            "failed",
            "The worker this job was waiting for was disconnected from your account.",
        )
    logger.info("Worker revoked", extra={"worker_id": worker.id})


# -------------------------------------------------------------- job leasing
def requeue_expired(database: Database, storage: LocalStorage, settings: Settings) -> int:
    """Give jobs back to the queue when their worker went silent. Returns how many changed."""
    now = utcnow()
    to_finish: list[tuple[str, str, str | None]] = []
    changed = 0
    with database.session_scope() as db:
        stale = db.scalars(
            select(Job).where(
                Job.status == "running",
                Job.lease_expires_at.is_not(None),
                Job.lease_expires_at < now,
            )
        ).all()
        for job in stale:
            changed += 1
            if job.cancel_requested:
                to_finish.append((job.id, "cancelled", None))
            elif job.attempts >= settings.worker_job_max_attempts:
                to_finish.append((job.id, "failed", WORKER_GONE))
            else:
                job.status = "queued"
                job.lease_expires_at = None
                job.stage = "Waiting for your worker to reconnect"
    for job_id, outcome, message in to_finish:
        finish_job(database, storage, job_id, outcome, message)  # type: ignore[arg-type]
    return changed


def claim_next_job(
    database: Database, storage: LocalStorage, settings: Settings, worker_id: str
) -> tuple[str, dict[str, Any]] | None:
    """Atomically hand the oldest waiting job of this worker's owner to the worker."""
    requeue_expired(database, storage, settings)
    for _ in range(5):
        with database.session_scope() as db:
            worker = db.get(Worker, worker_id)
            if worker is None or worker.status != "active":
                return None
            job = db.scalar(
                select(Job)
                .where(
                    Job.owner_id == worker.owner_id,
                    Job.status == "queued",
                    or_(Job.worker_id == worker.id, Job.worker_id.is_(None)),
                )
                .order_by(Job.created_at)
                .limit(1)
            )
            if job is None:
                return None
            job_id = job.id
            if job.cancel_requested:
                cancelled = True
            else:
                cancelled = False
                now = utcnow()
                taken = db.execute(
                    update(Job)
                    .where(Job.id == job_id, Job.status == "queued")
                    .values(
                        status="running",
                        worker_id=worker.id,
                        started_at=now,
                        lease_expires_at=now + timedelta(seconds=settings.worker_lease_seconds),
                        attempts=Job.attempts + 1,
                        stage="Starting",
                    )
                )
                if taken.rowcount != 1:
                    continue  # another request took it first
        if cancelled:
            finish_job(database, storage, job_id, "cancelled")
            continue
        try:
            with database.session_scope() as db:
                job = db.get(Job, job_id)
                if job is None:
                    continue
                project = db.get(Project, job.project_id) if job.project_id else None
                if project is not None and project.worker_id is None:
                    project.worker_id = worker_id  # this worker will hold the project's files
                spec = build_spec(db, settings, storage, job)
            return job_id, spec
        except ProcessingError as exc:
            finish_job(database, storage, job_id, "failed", exc.user_message)
    return None


def running_job_for_worker(db: Session, settings: Settings, worker: Worker, job_id: str) -> Job:
    """The job, if this worker currently holds it. Re-acquires a lease lost to a short outage."""
    job = db.scalar(
        select(Job).where(
            Job.id == job_id, Job.owner_id == worker.owner_id, Job.worker_id == worker.id
        )
    )
    if job is None:
        raise NotFoundError("Job not found.")
    if job.status == "queued" and job.attempts > 0 and not job.cancel_requested:
        # The lease expired during a brief disconnection, but the worker is still on it.
        job.status = "running"
        job.stage = "Reconnected"
    if job.status != "running":
        raise ConflictError("This job is no longer active.", code="job_not_active")
    job.lease_expires_at = utcnow() + timedelta(seconds=settings.worker_lease_seconds)
    return job


# ---------------------------------------------------------- transfer tokens
def create_transfer_token(
    db: Session,
    settings: Settings,
    *,
    owner_id: str,
    worker: Worker,
    scope: str,
    project: Project | None,
) -> tuple[str, TransferToken]:
    now = utcnow()
    db.execute(delete(TransferToken).where(TransferToken.expires_at < now))
    if scope == "upload":
        if project is None:
            raise UnprocessableError("Choose the project this upload belongs to.")
        if project.source_type == "url":
            raise ConflictError("This project gets its video from a link.")
        if project.status not in ("awaiting_upload", "failed") or project.media_key:
            raise ConflictError("This project already has a video.", code="media_exists")
    token = TRANSFER_TOKEN_PREFIX + secrets.token_urlsafe(32)
    row = TransferToken(
        token_hash=hash_token(token),
        owner_id=owner_id,
        worker_id=worker.id,
        scope=scope,
        project_id=project.id if project is not None and scope == "upload" else None,
        expires_at=now + timedelta(minutes=settings.transfer_token_minutes),
    )
    db.add(row)
    db.commit()
    return token, row


def verify_transfer_token(db: Session, worker: Worker, token: str) -> TransferToken:
    """Check a token presented to ``worker``'s bridge. Tokens for other workers never verify."""
    denied = ForbiddenError(
        "This transfer link is not valid any more.", code="invalid_transfer_token"
    )
    if not token or not token.startswith(TRANSFER_TOKEN_PREFIX) or len(token) > 200:
        raise denied
    row = db.scalar(select(TransferToken).where(TransferToken.token_hash == hash_token(token)))
    if (
        row is None
        or row.worker_id != worker.id
        or row.owner_id != worker.owner_id
        or row.expires_at <= utcnow()
    ):
        raise denied
    return row
