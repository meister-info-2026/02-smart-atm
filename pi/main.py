"""라즈베리파이 5 ATM 데몬.

역할
  1) 카메라로 QR을 인식해 로컬에서 즉시 SAFE/CAUTION/DANGER를 판단한다
  2) 판단 결과에 따라 MG996R 현금 배출 장치를 제어하거나 차단한다
  3) 7인치 터치 화면(Next.js /atm 라우트)이 읽을 로컬 HTTP API를 제공한다
  4) 콜센터 확인 결과를 백엔드에서 몇 초마다 폴링한다

실행
  cd pi
  python3 -m venv venv && source venv/bin/activate
  pip install -r requirements.txt
  python main.py            # http://localhost:8100

hardware-rules.md: 실기기에 붙이기 전에 반드시 DEVICE_MODE=mock으로 먼저 검증한다.
"""
import asyncio
import logging
import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CURRENT_DIR.parent / "backend"
for path in (CURRENT_DIR, BACKEND_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(CURRENT_DIR / ".env")

import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from atm_controller import AtmController  # noqa: E402
from backend_client import BackendClient  # noqa: E402
from iot.provider_factory import create_provider  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("pi.main")

CALL_CENTER_POLL_SECONDS = float(os.getenv("CALL_CENTER_POLL_SECONDS", "3"))
DAEMON_PORT = int(os.getenv("ATM_DAEMON_PORT", "8100"))
CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "0"))
ENABLE_CAMERA = os.getenv("ENABLE_CAMERA", "true").strip().lower() != "false"

provider = create_provider()
controller = AtmController(provider, BackendClient())

_stop = threading.Event()
_event_loop: asyncio.AbstractEventLoop | None = None


def _on_qr_detected(raw: str) -> None:
    """카메라 스레드에서 호출된다 — 처리 자체는 이벤트 루프에 넘긴다."""
    logger.info("QR 인식: %s", raw[:80])
    if _event_loop is None:
        return
    asyncio.run_coroutine_threadsafe(controller.handle_qr(raw), _event_loop)


async def _poll_call_center() -> None:
    """콜센터 확인 결과를 주기적으로 반영한다 (desired-state 폴링과 같은 패턴)."""
    while not _stop.is_set():
        if controller.session_id and controller.state in ("WITHDRAW_BLOCKED", "CALL_CENTER"):
            await controller.refresh_from_backend()
        await asyncio.sleep(CALL_CENTER_POLL_SECONDS)


async def _auto_reset_when_idle() -> None:
    """앞사람이 남긴 화면을 치우고 기계를 다음 사람에게 넘긴다.

    1초마다 보는 이유는 화면의 카운트다운과 어긋나지 않게 하기 위해서다.
    실제로 되돌릴 것이 없으면 아무 일도 하지 않는다.
    """
    while not _stop.is_set():
        controller.reset_if_idle()
        await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _event_loop
    _event_loop = asyncio.get_running_loop()

    poller = asyncio.create_task(_poll_call_center())
    idle_watch = asyncio.create_task(_auto_reset_when_idle())
    camera_thread: threading.Thread | None = None

    if ENABLE_CAMERA:
        from qr_scanner import scan_loop

        def _run_camera() -> None:
            try:
                scan_loop(_on_qr_detected, CAMERA_INDEX, _stop.is_set)
            except Exception as exc:  # noqa: BLE001
                logger.error("카메라 스캔을 시작하지 못했습니다: %s", exc)
                logger.error("카메라 없이 시연하려면 .env에 ENABLE_CAMERA=false를 넣고 "
                             "POST /qr 로 session_id를 직접 넣으세요.")

        camera_thread = threading.Thread(target=_run_camera, daemon=True)
        camera_thread.start()
    else:
        logger.info("ENABLE_CAMERA=false — 카메라 없이 POST /qr 로 시연합니다.")

    yield

    _stop.set()
    poller.cancel()
    idle_watch.cancel()
    if camera_thread:
        camera_thread.join(timeout=2)


app = FastAPI(title="ATM 로컬 제어 데몬", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 파이 내부(localhost)에서만 뜨는 화면이라 넓게 둔다
    allow_methods=["*"],
    allow_headers=["*"],
)


class QrRequest(BaseModel):
    """카메라 없이 QR 내용을 직접 넣을 때 쓴다 (시연 백업 절차)."""

    data: str


class WithdrawRequest(BaseModel):
    amount: int | None = None


@app.get("/state")
async def read_state() -> dict:
    """7인치 화면이 폴링하는 현재 ATM 상태."""
    return {"data": controller.snapshot()}


@app.post("/qr")
async def submit_qr(payload: QrRequest) -> dict:
    """QR 문자열을 직접 넣어 처리한다."""
    return {"data": await controller.handle_qr(payload.data)}


@app.post("/withdraw")
async def withdraw(payload: WithdrawRequest) -> dict:
    """출금 버튼. WITHDRAW_ENABLED가 아니면 배출 장치를 건드리지 않는다."""
    return {"data": await controller.request_withdraw(payload.amount)}


@app.post("/call-center")
async def call_center() -> dict:
    """콜센터 확인 단계로 넘어간다."""
    return {"data": await controller.enter_call_center()}


@app.post("/reset")
async def reset() -> dict:
    """다음 사용자를 위해 대기 상태로 되돌린다."""
    controller.reset()
    return {"data": controller.snapshot()}


if __name__ == "__main__":
    logger.info("ATM 데몬 시작 — DEVICE_MODE=%s, port=%d", os.getenv("DEVICE_MODE", "mock"), DAEMON_PORT)
    uvicorn.run(app, host="0.0.0.0", port=DAEMON_PORT)
