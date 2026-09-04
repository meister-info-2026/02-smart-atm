"""통합 시연 자동 검증 스크립트 (FR-12 / PRD 9.1·9.2·10.5).

실제로 띄워 둔 백엔드와 ATM 데몬에 HTTP로 붙어서, 문자 분석부터 콜센터 확인까지
한 번에 이어지는지 확인한다. QR도 실제 PNG로 만들어 OpenCV로 디코딩한다.

준비
  1) backend: cd backend && python -m db.seed && uvicorn main:app --port 8000
  2) pi:      cd pi && python main.py          (.env에 ENABLE_CAMERA=false)
실행
  python scripts/demo_e2e.py
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import requests

BACKEND = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
ATM_DAEMON = os.getenv("ATM_DAEMON_URL", "http://127.0.0.1:8100")
DEVICE_KEY = os.getenv("DEVICE_API_KEY", "")
PASSWORD = os.getenv("SEED_DEFAULT_PASSWORD", "demo1234")

NORMAL_MESSAGE = "오늘 오후 3시에 병원 예약이 있습니다."
PHISHING_MESSAGE = (
    "검찰입니다. 계좌가 범죄에 연루되었습니다. 현금 500만 원을 인출해 지정 장소로 가져오세요."
)

POLL_TIMEOUT_SECONDS = 15
failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if ok else 'FAIL'} {label}{f' — {detail}' if detail else ''}")
    if not ok:
        failures.append(label)


def login(username: str) -> dict[str, str]:
    response = requests.post(
        f"{BACKEND}/api/v1/auth/login",
        json={"username": username, "password": PASSWORD},
        timeout=10,
    )
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def analyze(headers: dict[str, str], message: str) -> dict:
    response = requests.post(
        f"{BACKEND}/api/v1/analysis", json={"message": message}, headers=headers, timeout=10
    )
    response.raise_for_status()
    return response.json()["data"]


def make_and_read_qr(session_id: str) -> str:
    """프론트엔드처럼 QR 이미지를 만들고, ATM 카메라처럼 다시 읽어낸다."""
    import cv2
    import qrcode

    payload = json.dumps({"session_id": session_id})
    path = Path(tempfile.gettempdir()) / f"demo_{session_id}.png"
    qrcode.make(payload).save(path)

    decoded, _points, _straight = cv2.QRCodeDetector().detectAndDecode(cv2.imread(str(path)))
    if not decoded:
        raise RuntimeError("생성한 QR을 다시 읽지 못했습니다.")
    return decoded


def atm_post(path: str, body: dict | None = None) -> dict:
    response = requests.post(f"{ATM_DAEMON}{path}", json=body or {}, timeout=10)
    response.raise_for_status()
    return response.json()["data"]


def wait_for_state(expected: str) -> dict:
    """ATM이 콜센터 폴링으로 상태를 바꿀 때까지 기다린다."""
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    state: dict = {}
    while time.monotonic() < deadline:
        state = requests.get(f"{ATM_DAEMON}/state", timeout=10).json()["data"]
        if state.get("state") == expected:
            return state
        time.sleep(1)
    return state


def scenario_safe(user: dict[str, str]) -> None:
    print("\n[시나리오 1] 정상 문자 → 출금 제한 없음 (PRD 9.1 / TC-01)")
    result = analyze(user, NORMAL_MESSAGE)
    check("분석 결과가 SAFE", result["risk_level"] == "SAFE", f"score={result['risk_score']}")

    atm_post("/reset")
    state = atm_post("/qr", {"data": make_and_read_qr(result["session_id"])})
    check("ATM이 출금 가능 상태로 전환", state["state"] == "WITHDRAW_ENABLED")

    withdrawn = atm_post("/withdraw", {"amount": 50000})
    check("현금이 실제로 배출됨 (FR-08)", withdrawn["dispensed"] is True)


def scenario_danger(user: dict[str, str], agent: dict[str, str]) -> None:
    print("\n[시나리오 2] 보이스피싱 문자 → 출금 차단 → 콜센터 해제 (PRD 9.2 / TC-02·TC-05)")
    result = analyze(user, PHISHING_MESSAGE)
    check("분석 결과가 DANGER", result["risk_level"] == "DANGER", f"score={result['risk_score']}")
    check("탐지 근거가 표시됨 (FR-04)", len(result["reasons"]) > 0, ", ".join(result["reasons"]))
    session_id = result["session_id"]

    atm_post("/reset")
    state = atm_post("/qr", {"data": make_and_read_qr(session_id)})
    check("ATM이 출금 제한 상태로 전환 (FR-07)", state["state"] == "WITHDRAW_BLOCKED")

    blocked = atm_post("/withdraw", {"amount": 500000})
    check("출금 버튼을 눌러도 배출되지 않음 (FR-09)", blocked["dispensed"] is False)

    atm_post("/call-center")
    check("콜센터 확인 단계로 전환 (FR-11)", wait_for_state("CALL_CENTER")["state"] == "CALL_CENTER")

    sessions = requests.get(
        f"{BACKEND}/api/v1/callcenter/sessions?only_open=false", headers=agent, timeout=10
    ).json()["data"]
    check(
        "상담원 화면에 세션이 보임 (PRD 8.2)",
        any(s["session_id"] == session_id for s in sessions),
    )

    requests.post(
        f"{BACKEND}/api/v1/callcenter/resolve/{session_id}",
        json={"resolution": "RELEASED", "note": "본인 확인 완료"},
        headers=agent,
        timeout=10,
    ).raise_for_status()

    released = wait_for_state("WITHDRAW_ENABLED")
    check("콜센터 해제 후 출금이 열림 (TC-05)", released["state"] == "WITHDRAW_ENABLED")
    check("해제 후 현금 배출 성공", atm_post("/withdraw", {"amount": 50000})["dispensed"] is True)


def scenario_bad_qr() -> None:
    print("\n[시나리오 3] 잘못된 QR → 거래 제어에 사용하지 않음 (PRD 10.4 / TC-04)")
    atm_post("/reset")
    state = atm_post("/qr", {"data": '{"session_id": "VP-999999"}'})
    check("등록되지 않은 QR을 거부", state["state"] == "READY" and bool(state["last_error"]))
    check("현금 배출 불가", atm_post("/withdraw", {"amount": 50000})["dispensed"] is False)

    state = atm_post("/qr", {"data": "{깨진 데이터}"})
    check("형식이 잘못된 QR을 거부", bool(state["last_error"]))


def scenario_callcenter_permission(user: dict[str, str]) -> None:
    print("\n[시나리오 4] 사용자는 스스로 제한을 풀 수 없다 (PRD 8)")
    result = analyze(user, PHISHING_MESSAGE)
    session_id = result["session_id"]

    listed = requests.get(f"{BACKEND}/api/v1/callcenter/sessions", headers=user, timeout=10)
    check("일반 사용자는 콜센터 목록 접근 불가", listed.status_code == 403)

    released = requests.post(
        f"{BACKEND}/api/v1/callcenter/resolve/{session_id}",
        json={"resolution": "RELEASED"},
        headers=user,
        timeout=10,
    )
    check("일반 사용자는 제한 해제 불가", released.status_code == 403)

    status = requests.get(
        f"{BACKEND}/api/v1/atm/session-status/{session_id}",
        headers={"X-Device-Api-Key": DEVICE_KEY},
        timeout=10,
    )
    if status.status_code == 200:
        check("제한이 그대로 유지됨", status.json()["data"]["action"] == "BLOCK")


def scenario_device_auth() -> None:
    print("\n[시나리오 5] 인증 분리 확인 (api-rules.md)")
    no_key = requests.get(f"{BACKEND}/api/v1/atm/verify/VP-000001", timeout=10)
    check("디바이스 키 없이 ATM API 접근 차단", no_key.status_code == 401)

    if DEVICE_KEY:
        with_key = requests.get(
            f"{BACKEND}/api/v1/users/me", headers={"X-Device-Api-Key": DEVICE_KEY}, timeout=10
        )
        check("디바이스 키로 사용자 API 접근 차단", with_key.status_code == 401)


def main() -> int:
    print(f"백엔드: {BACKEND}\nATM 데몬: {ATM_DAEMON}")
    user = login("halmeoni")
    agent = login("callcenter")

    scenario_safe(user)
    scenario_danger(user, agent)
    scenario_bad_qr()
    scenario_callcenter_permission(user)
    scenario_device_auth()
    atm_post("/reset")

    print("\n" + "=" * 60)
    if failures:
        print(f"실패 {len(failures)}건: " + ", ".join(failures))
        return 1
    print("통합 시연 전 구간 통과 — 정상 문자와 보이스피싱 문자 모두 확인했습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
