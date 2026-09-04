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

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import get_settings
from db.database import init_db
from routers import analysis, atm, auth, callcenter, chats, friends, health, users
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
async def websocket_endpoint(websocket: WebSocket):
    """실시간 ATM/콜센터 상태 스트리밍용 WebSocket 엔드포인트"""
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)
