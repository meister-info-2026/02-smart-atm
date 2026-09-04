"""DB 엔진/세션 생성.

운영은 MySQL(`mysql+pymysql://`), 테스트/시연 백업은 SQLite를 쓴다.
어느 쪽을 쓸지는 config.Settings.database_url이 결정한다.
"""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config import get_settings

from .models import Base

_settings = get_settings()

_engine_kwargs: dict = {"pool_pre_ping": True, "future": True}
if _settings.is_sqlite:
    # SQLite는 커넥션 풀 옵션이 다르고, 같은 커넥션을 여러 스레드에서 써야 한다
    _engine_kwargs = {"connect_args": {"check_same_thread": False}, "future": True}

engine = create_engine(_settings.database_url, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    """테이블이 없으면 만든다 (db-integration 스킬의 init_db 패턴)."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 의존성 주입용 DB 세션."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
