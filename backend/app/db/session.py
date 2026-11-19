"""Engine and session management."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker


def _sqlite_pragmas(dbapi_connection, _record) -> None:  # type: ignore[no-untyped-def]
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


class Database:
    """Owns the SQLAlchemy engine and hands out sessions."""

    def __init__(self, url: str, *, small_pool: bool = False) -> None:
        self.url = url
        self.is_sqlite = url.startswith("sqlite")
        if self.is_sqlite:
            db_path = url.split("///", 1)[-1]
            if db_path and db_path != ":memory:":
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            self.engine: Engine = create_engine(
                url, connect_args={"check_same_thread": False, "timeout": 30}
            )
            event.listen(self.engine, "connect", _sqlite_pragmas)
        else:
            self.engine = create_engine(
                url,
                pool_pre_ping=True,
                pool_size=1 if small_pool else 5,
                max_overflow=2 if small_pool else 10,
                pool_recycle=300,
                # No server-side prepared statements: they break behind transaction-mode
                # connection poolers (PgBouncer, Neon's pooled URL, Supabase's pooler).
                connect_args={"prepare_threshold": None},
            )
        self._factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def session(self) -> Session:
        return self._factory()

    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        """Session that commits on success and rolls back on error."""
        session = self._factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def ping(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception:
            return False
        return True

    def dispose(self) -> None:
        self.engine.dispose()
