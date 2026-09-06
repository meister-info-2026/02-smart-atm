"""전체 흐름 통합 테스트 (PRD 9장 시스템 동작 흐름 / 14.2 테스트 계획).

문자 분석 → QR용 session_id → ATM 서버 검증 → 출금 제한 → 콜센터 확인까지
한 번에 이어지는지 확인한다.
"""
from fastapi.testclient import TestClient

NORMAL_MESSAGE = "오늘 오후 3시에 병원 예약이 있습니다."
PHISHING_MESSAGE = (
    "검찰입니다. 계좌가 범죄에 연루되었습니다. 현금 500만 원을 인출해 지정 장소로 가져오세요."
)


def _analyze(client: TestClient, headers: dict[str, str], message: str) -> dict:
    response = client.post("/api/v1/analysis", json={"message": message}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


# ── 인증 분리 (api-rules.md — 반드시 지킬 것) ──────────────────────────────────
def test_user_endpoint_rejects_device_key(
    client: TestClient, device_headers: dict[str, str]
) -> None:
    """사용자향 엔드포인트는 디바이스 키만으로 접근할 수 없다."""
    response = client.get("/api/v1/users/me", headers=device_headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_device_endpoint_rejects_user_jwt(
    client: TestClient, user_headers: dict[str, str]
) -> None:
    """디바이스향 엔드포인트는 사용자 JWT를 받지 않는다."""
    response = client.get("/api/v1/atm/verify/VP-000001", headers=user_headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED_DEVICE"


def test_login_with_wrong_password_fails(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"username": "halmeoni", "password": "wrong"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


# ── 채팅/문자 선택 (FR-01) ───────────────────────────────────────────────────
def test_chat_list_and_message_analysis(
    client: TestClient, user_headers: dict[str, str]
) -> None:
    """채팅 목록에서 문자를 골라 분석할 수 있다."""
    chats = client.get("/api/v1/chats", headers=user_headers).json()["data"]
    assert len(chats) >= 3

    phishing_chat = next(c for c in chats if "500-0000" in c["title"])
    messages = client.get(
        f"/api/v1/chats/{phishing_chat['id']}/messages", headers=user_headers
    ).json()["data"]
    assert messages

    response = client.post(
        f"/api/v1/analysis/chats/{phishing_chat['id']}",
        json={"message_id": messages[0]["id"]},
        headers=user_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["risk_level"] == "DANGER"


# ── TC-01 정상 문자 시나리오 (PRD 9.1) ───────────────────────────────────────
def test_tc01_safe_flow_allows_withdrawal(
    client: TestClient, user_headers: dict[str, str], device_headers: dict[str, str]
) -> None:
    """정상 문자 → SAFE → ATM 검증 결과 ALLOW → 출금 제한 없음."""
    analysis = _analyze(client, user_headers, NORMAL_MESSAGE)
    assert analysis["risk_level"] == "SAFE"
    assert analysis["atm_action"] == "ALLOW"

    verify = client.get(
        f"/api/v1/atm/verify/{analysis['session_id']}", headers=device_headers
    ).json()["data"]
    assert verify["action"] == "ALLOW"
    assert verify["atm_status"] == "WITHDRAW_ENABLED"


# ── TC-02 보이스피싱 시나리오 (PRD 9.2) ──────────────────────────────────────
def test_tc02_danger_flow_blocks_withdrawal_until_callcenter(
    client: TestClient,
    user_headers: dict[str, str],
    callcenter_headers: dict[str, str],
    device_headers: dict[str, str],
) -> None:
    """DANGER → QR 검증 BLOCK → 스캔 보고 → 콜센터가 해제해야만 ALLOW로 바뀐다."""
    analysis = _analyze(client, user_headers, PHISHING_MESSAGE)
    assert analysis["risk_level"] == "DANGER"
    assert analysis["reasons"], "탐지 근거가 표시되어야 한다 (FR-04)"
    session_id = analysis["session_id"]

    # QR 표시용 ATM 세션 조회 (QR에는 session_id만 들어간다)
    atm_session = client.get(
        f"/api/v1/analysis/{analysis['analysis_id']}/atm", headers=user_headers
    ).json()["data"]
    assert atm_session["session_id"] == session_id

    # ATM이 QR을 읽고 서버에서 검증한다
    verify = client.get(
        f"/api/v1/atm/verify/{session_id}", headers=device_headers
    ).json()["data"]
    assert verify["action"] == "BLOCK"

    # ATM이 스캔 결과를 보고하고 콜센터 확인 상태로 전환한다
    scan = client.post(
        "/api/v1/atm/scan",
        json={"session_id": session_id, "atm_status": "CALL_CENTER"},
        headers=device_headers,
    )
    assert scan.status_code == 200, scan.text
    assert scan.json()["data"]["atm_status"] == "CALL_CENTER"

    # 시스템이 스스로 풀지 않는다 — 폴링해도 여전히 BLOCK이다
    status = client.get(
        f"/api/v1/atm/session-status/{session_id}", headers=device_headers
    ).json()["data"]
    assert status["action"] == "BLOCK"
    assert status["callcenter_resolution"] is None

    # 상담원 화면에 확인 대상으로 나타난다 (PRD 8.2)
    sessions = client.get(
        "/api/v1/callcenter/sessions", headers=callcenter_headers
    ).json()["data"]
    assert any(s["session_id"] == session_id for s in sessions)


# ── TC-05 콜센터 정상 확인 후 제한 해제 (PRD 10.5) ───────────────────────────
def test_tc05_callcenter_release_unblocks_atm(
    client: TestClient,
    user_headers: dict[str, str],
    callcenter_headers: dict[str, str],
    device_headers: dict[str, str],
) -> None:
    """AI가 위험으로 봤지만 콜센터가 정상 거래로 확인하면 제한이 해제된다."""
    analysis = _analyze(client, user_headers, PHISHING_MESSAGE)
    session_id = analysis["session_id"]

    resolved = client.post(
        f"/api/v1/callcenter/resolve/{session_id}",
        json={"resolution": "RELEASED", "note": "본인 확인 완료, 정상 거래"},
        headers=callcenter_headers,
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["data"]["atm_status"] == "WITHDRAW_ENABLED"

    status = client.get(
        f"/api/v1/atm/session-status/{session_id}", headers=device_headers
    ).json()["data"]
    assert status["action"] == "ALLOW"
    assert status["callcenter_resolution"] == "RELEASED"


def test_callcenter_maintain_keeps_block(
    client: TestClient,
    user_headers: dict[str, str],
    callcenter_headers: dict[str, str],
    device_headers: dict[str, str],
) -> None:
    """보이스피싱으로 확인되면 제한을 유지한다 (PRD 8.3)."""
    analysis = _analyze(client, user_headers, PHISHING_MESSAGE)
    session_id = analysis["session_id"]

    client.post(
        f"/api/v1/callcenter/resolve/{session_id}",
        json={"resolution": "MAINTAINED", "note": "보이스피싱 의심 지속"},
        headers=callcenter_headers,
    )
    status = client.get(
        f"/api/v1/atm/session-status/{session_id}", headers=device_headers
    ).json()["data"]
    assert status["action"] == "BLOCK"
    assert status["atm_status"] == "WITHDRAW_BLOCKED"


# ── TC-04 잘못된 QR (PRD 10.4) ───────────────────────────────────────────────
def test_tc04_unknown_session_is_rejected(
    client: TestClient, device_headers: dict[str, str]
) -> None:
    """등록되지 않은 QR은 거래 제어 데이터로 쓰지 않고 오류로 돌려준다."""
    response = client.get("/api/v1/atm/verify/VP-999999", headers=device_headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SESSION_NOT_FOUND"


def test_scan_with_unknown_session_is_rejected(
    client: TestClient, device_headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/v1/atm/scan",
        json={"session_id": "VP-999999", "atm_status": "WITHDRAW_BLOCKED"},
        headers=device_headers,
    )
    assert response.status_code == 404


# ── 기록 저장 (OF-05) ────────────────────────────────────────────────────────
def test_analysis_record_can_be_read_back(
    client: TestClient, user_headers: dict[str, str]
) -> None:
    """분석 결과가 저장되어 나중에 다시 조회된다."""
    analysis = _analyze(client, user_headers, PHISHING_MESSAGE)
    again = client.get(
        f"/api/v1/analysis/{analysis['analysis_id']}", headers=user_headers
    ).json()["data"]
    assert again["risk_level"] == analysis["risk_level"]
    assert again["reasons"] == analysis["reasons"]


def test_health_endpoints(client: TestClient) -> None:
    assert client.get("/health").json()["data"]["status"] == "ok"
    assert client.get("/health/db").json()["data"]["status"] == "ok"


# ── 콜센터 권한 (PRD 8: 사용자 본인이 스스로 제한을 풀 수 없다) ─────────────
def test_regular_user_cannot_open_callcenter_screen(
    client: TestClient, user_headers: dict[str, str]
) -> None:
    """일반 사용자는 콜센터 화면 데이터를 볼 수 없다."""
    response = client.get("/api/v1/callcenter/sessions", headers=user_headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_regular_user_cannot_release_own_block(
    client: TestClient, user_headers: dict[str, str], device_headers: dict[str, str]
) -> None:
    """제한을 받은 사용자가 스스로 제한을 해제할 수 없다."""
    analysis = _analyze(client, user_headers, PHISHING_MESSAGE)
    session_id = analysis["session_id"]

    response = client.post(
        f"/api/v1/callcenter/resolve/{session_id}",
        json={"resolution": "RELEASED"},
        headers=user_headers,
    )
    assert response.status_code == 403

    status = client.get(
        f"/api/v1/atm/session-status/{session_id}", headers=device_headers
    ).json()["data"]
    assert status["action"] == "BLOCK", "본인 요청으로 제한이 풀리면 안 된다"


def test_me_exposes_role(client: TestClient, callcenter_headers: dict[str, str]) -> None:
    me = client.get("/api/v1/users/me", headers=callcenter_headers).json()["data"]
    assert me["role"] == "agent"


# ── 디바이스가 스스로 제한을 풀 수 없다 (db-rules.md 경보성 디바이스 원칙) ──
def test_device_cannot_open_withdrawal_without_callcenter(
    client: TestClient, user_headers: dict[str, str], device_headers: dict[str, str]
) -> None:
    """ATM이 WITHDRAW_ENABLED를 보고해도 콜센터 확인 전에는 받아 주지 않는다.

    이 검사가 없으면 디바이스 키를 가진 쪽이 스캔 보고 한 번으로 DANGER 판정을
    뒤집을 수 있어, 사람의 확인을 거치게 한 설계 자체가 무의미해진다.
    """
    analysis = _analyze(client, user_headers, PHISHING_MESSAGE)
    session_id = analysis["session_id"]

    response = client.post(
        "/api/v1/atm/scan",
        json={"session_id": session_id, "atm_status": "WITHDRAW_ENABLED"},
        headers=device_headers,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RELEASE_NOT_AUTHORIZED"

    status = client.get(
        f"/api/v1/atm/session-status/{session_id}", headers=device_headers
    ).json()["data"]
    assert status["action"] == "BLOCK"
    assert status["atm_status"] != "WITHDRAW_ENABLED"


def test_device_may_report_enabled_after_callcenter_release(
    client: TestClient,
    user_headers: dict[str, str],
    callcenter_headers: dict[str, str],
    device_headers: dict[str, str],
) -> None:
    """반대로 상담원이 해제한 뒤에는 정상 보고로 받아들인다."""
    analysis = _analyze(client, user_headers, PHISHING_MESSAGE)
    session_id = analysis["session_id"]
    client.post(
        f"/api/v1/callcenter/resolve/{session_id}",
        json={"resolution": "RELEASED"},
        headers=callcenter_headers,
    )

    response = client.post(
        "/api/v1/atm/scan",
        json={"session_id": session_id, "atm_status": "WITHDRAW_ENABLED"},
        headers=device_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["action"] == "ALLOW"


def test_safe_session_may_be_reported_as_enabled(
    client: TestClient, user_headers: dict[str, str], device_headers: dict[str, str]
) -> None:
    """SAFE 문자는 애초에 제한 대상이 아니므로 그대로 출금 가능으로 보고된다."""
    analysis = _analyze(client, user_headers, NORMAL_MESSAGE)
    response = client.post(
        "/api/v1/atm/scan",
        json={"session_id": analysis["session_id"], "atm_status": "WITHDRAW_ENABLED"},
        headers=device_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["action"] == "ALLOW"


# ── 남의 채팅방 문자를 분석 경로로 읽을 수 없다 ──────────────────────────────
def test_analysis_rejects_other_users_chat_room(
    client: TestClient, user_headers: dict[str, str]
) -> None:
    """내가 속하지 않은 채팅방은 분석 요청으로도 열어 볼 수 없다.

    응답에 문자 원문이 실리므로, 목록 조회(GET /chats/{id}/messages)만 막고
    이 경로를 열어 두면 남의 문자를 그대로 읽을 수 있다.
    """
    friend_headers = {
        "Authorization": "Bearer "
        + client.post(
            "/api/v1/auth/login", json={"username": "friend01", "password": "test1234"}
        ).json()["data"]["access_token"]
    }
    chats = client.get("/api/v1/chats", headers=user_headers).json()["data"]
    other_room_id = chats[0]["id"]
    assert client.get("/api/v1/chats", headers=friend_headers).json()["data"] == []

    response = client.post(
        f"/api/v1/analysis/chats/{other_room_id}", json={}, headers=friend_headers
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CHAT_NOT_FOUND"


# ── 세션 번호는 지운 뒤에도 겹치지 않는다 ────────────────────────────────────
def test_session_id_survives_deleted_rows(
    client: TestClient, user_headers: dict[str, str]
) -> None:
    """시연 정리로 지난 세션을 지워도 다음 분석이 UNIQUE 제약에 걸리지 않는다.

    번호를 '행 개수 + 1'로 매기면 오래된 행을 지우는 순간 살아 있는 번호가 다시
    나와, 그 뒤 모든 분석 요청이 500으로 실패한다.
    """
    from db.database import SessionLocal
    from db.models import AtmSession

    older = _analyze(client, user_headers, PHISHING_MESSAGE)
    newer = _analyze(client, user_headers, PHISHING_MESSAGE)

    with SessionLocal() as db:  # 지난 세션 한 건만 정리한다
        db.delete(
            db.query(AtmSession).filter(AtmSession.session_id == older["session_id"]).one()
        )
        db.commit()

    again = _analyze(client, user_headers, PHISHING_MESSAGE)
    assert again["session_id"] != newer["session_id"]
