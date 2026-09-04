"""애플리케이션 설정 (.env 로드).

security-rules.md: 시크릿 값은 코드에 하드코딩하지 않고 전부 .env로 관리한다.
"""
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

# ── 위험 등급 경계값 (PRD 5.2 — 임의로 바꾸지 않는다) ──────────────────────────
RISK_SAFE_MAX = 29
RISK_CAUTION_MAX = 69
RISK_SCORE_MAX = 100

# ── ATM 세션 ID 형식 (PRD 5.8: "VP-000003") ─────────────────────────────────
SESSION_ID_PREFIX = "VP-"
SESSION_ID_DIGITS = 6


class Settings:
    """환경변수를 한 곳에서 읽어오는 설정 객체."""

    def __init__(self) -> None:
        self.device_mode: str = os.getenv("DEVICE_MODE", "mock").strip().lower()

        # DB — 운영은 MySQL, 테스트는 SQLite 폴백 (DATABASE_URL로 덮어쓸 수 있다)
        self.db_host: str = os.getenv("DB_HOST", "127.0.0.1")
        self.db_port: int = int(os.getenv("DB_PORT", "3306"))
        self.db_user: str = os.getenv("DB_USER", "root")
        self.db_password: str = os.getenv("DB_PASSWORD", "")
        self.db_name: str = os.getenv("DB_NAME", "smart_atm")
        self._database_url_override: str = os.getenv("DATABASE_URL", "").strip()

        # 인증 — 사용자향(JWT) / 디바이스향(API 키) 분리 (api-rules.md)
        self.jwt_secret: str = os.getenv("JWT_SECRET", "")
        self.jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
        self.jwt_expire_minutes: int = int(os.getenv("JWT_EXPIRE_MINUTES", "720"))
        self.device_api_key: str = os.getenv("DEVICE_API_KEY", "")

        self.cors_origins: list[str] = [
            origin.strip()
            for origin in os.getenv("CORS_ORIGINS", "*").split(",")
            if origin.strip()
        ]

    @property
    def database_url(self) -> str:
        """SQLAlchemy 접속 URL. DATABASE_URL이 있으면 그걸 우선한다."""
        if self._database_url_override:
            return self._database_url_override
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
