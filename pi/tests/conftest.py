"""pi 테스트 공통 설정 — pi/와 backend/를 임포트 경로에 넣는다."""
import sys
from pathlib import Path

PI_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = PI_DIR.parent / "backend"
for path in (PI_DIR, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
