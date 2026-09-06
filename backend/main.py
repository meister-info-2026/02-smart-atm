import os
import sys

# ==============================================================================
# sys.path 자동 경로 주입 (어느 디렉토리에서 실행하든 절대/상대 경로 임포트 오류 방지)
# ==============================================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.status import WS_1008_POLICY_VIOLATION

from config import get_settings
from db.database import SessionLocal, init_db
from routers import analysis, atm, auth, callcenter, chats, friends, health, users
from security.jwt_auth import agent_from_token
from websocket_manager import ws_manager

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """서버 시작 시 테이블 존재 여부를 확인/생성한다."""
    init_db()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="스마트 금융 보안 ATM API",
    version="1.0.0",
    description=(
        "노약자를 위한 AI 문자 보이스피싱 예방 시스템. "
        "문자 분석 → QR(session_id) → ATM 출금 제한 → 콜센터 확인."
    ),
)

# CORS 설정 (Next.js 로컬 개발 및 클라우드 배포 지원)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """실패 응답을 api-rules.md 형식으로 통일한다."""
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        error = detail
    else:
        error = {"code": f"HTTP_{exc.status_code}", "message": str(detail)}
    return JSONResponse(status_code=exc.status_code, content={"error": error})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """유효성 실패는 422로 돌려준다 (api-rules.md)."""
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "요청 형식이 올바르지 않습니다.",
                "details": exc.errors(),
            }
        },
    )


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(friends.router)
app.include_router(chats.router)
app.include_router(analysis.router)
app.include_router(atm.router)
app.include_router(callcenter.router)


@app.get("/")
async def root():
    """루트 안내 엔드포인트"""
    return {
        "data": {
            "message": "Smart Financial Security ATM Backend is active.",
            "docs_url": "/docs",
            "health_url": "/health",
        }
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str | None = Query(default=None)):
    """실시간 ATM/콜센터 상태 스트리밍용 WebSocket 엔드포인트.

    콜센터 상담원 화면 전용이다. 흘러가는 이벤트에 세션 번호와 위험 등급이 들어
    있어서, REST 쪽 콜센터 API와 같은 기준으로 상담원만 받는다
    (`require_callcenter_agent`와 짝을 이룬다).

    토큰은 `?token=<JWT>`로 받는다 — 브라우저 WebSocket API는 요청 헤더를 붙일 수
    없어 Authorization 헤더를 쓸 수 없다.
    """
    with SessionLocal() as db:  # 인증에만 쓰고 바로 닫는다 (연결 내내 붙들지 않는다)
        agent = agent_from_token(db, token)
    if agent is None:
        # 이유(1008)를 알려 주려면 핸드셰이크를 먼저 받아야 한다. accept 전에 닫으면
        # HTTP 403으로 끊겨서, 브라우저 쪽에서는 '서버가 죽음'과 구별할 수 없다.
        # 화면이 "권한 없음"과 "연결 끊김"을 다르게 안내할 수 있어야 한다.
        await websocket.accept()
        await websocket.close(code=WS_1008_POLICY_VIOLATION)
        return

    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)
