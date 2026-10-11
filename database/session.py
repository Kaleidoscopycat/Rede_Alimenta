"""Engine/sessão SQLAlchemy. A URL vem de DATABASE_URL (ambiente)."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from core.settings import database_url

_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _factory
    if _engine is None:
        _engine = create_engine(database_url(), pool_pre_ping=True, pool_size=10, max_overflow=10, future=True)
        _factory = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def reset_engine() -> None:
    global _engine, _factory
    if _engine is not None:
        _engine.dispose()
    _engine, _factory = None, None


def get_sessionmaker() -> sessionmaker[Session]:
    get_engine()
    if _factory is None:
        raise RuntimeError("fábrica de sessões não inicializada")
    return _factory


@contextmanager
def session_scope() -> Iterator[Session]:
    s = get_sessionmaker()()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
