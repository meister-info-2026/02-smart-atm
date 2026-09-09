# 스마트 금융 보안 ATM

> 노약자를 위한 AI 문자 보이스피싱 예방 시스템
> 2026학년도 2학년 IoT·영상인식 스마트 제어 시스템 팀 프로젝트

보이스피싱 의심 문자를 스마트폰에서 분석하고, 그 결과를 QR로 ATM에 전달해
**현금 인출을 막은 뒤** 콜센터 확인으로 최종 대응하는 시스템입니다.

## 이 작품이 보여주는 한 장면

> **위험 문자로 만든 QR을 ATM에 보여준 뒤 50만 원 버튼을 눌러도, 현금이 나오지 않는다.**

나머지는 이 한 장면을 설득하기 위한 앞뒤 맥락입니다.

## 어떻게 동작하나

```
어르신 휴대폰                 서버                    ATM                콜센터
─────────────              ────────              ────────           ────────
의심 문자 선택
      │
      └── 분석 요청 ──────▶ 규칙 기반 판정
                          SAFE / CAUTION / DANGER
                                │
      ◀── session_id ───────────┘
      │
   QR 표시 ─────────────────────────────────▶ QR 인식
   (위험할 때만)                                  │
                          서버 검증 ◀────────────┘
                                │
                          ALLOW/VERIFY/BLOCK ──▶ 출금 차단
                                                    │
                                              확인 요청 ──────▶ 상담원이 판단
                                                    │              │
                                              해제 / 유지 ◀────────┘
```

**ATM은 평상시에는 보통 ATM입니다.** 그 앞에 선 사람은 앱을 쓴 당사자일 수도,
가족일 수도, 이 시스템과 아무 상관 없는 사람일 수도 있습니다. QR이 없다고 출금을
막지 않고, **위험이 확인된 세션에서만** 막습니다.

## 지금 되는 것

| | 상태 |
|---|---|
| 문자 분석 (규칙 기반 7개 범주) | 동작 |
| QR 생성 · 인식 (`cv2.QRCodeDetector`) | 동작 |
| ATM 출금 차단 · 현금 배출 제어 | 동작 (Mock) |
| 콜센터 확인 (해제 / 유지) | 동작 |
| 음성 안내 (노약자용) | 동작 |
| 1분 무동작 시 자동 초기화 (제한 중에는 세지 않는다) | 동작 |
| 라즈베리파이 5 실기기 (서보 배출) | **2차 확장** — 코드는 있고 조립·핀맵이 남음 |
| 외부 AI API 분석 | **다음 단계** — 규칙 엔진은 백업으로 유지 |

## 빠른 시작

전체 절차는 **[docs/02 실행 가이드](./docs/02_스마트금융보안ATM-실행-가이드.md)** 에
있습니다. 처음이라면 그쪽을 보세요. 아래는 요약입니다.

```bash
# 0) .env 3개를 만든다 (backend / pi 의 DEVICE_API_KEY는 반드시 같은 값)
cp backend/.env.example backend/.env
cp pi/.env.example      pi/.env
cp frontend/.env.example frontend/.env.local

# 1) 백엔드
cd backend && pip install -r requirements.txt
python -m db.seed                      # 시연 계정·문자 생성
uvicorn main:app --reload --port 8000

# 2) ATM 데몬 (다른 터미널)
cd pi && pip install -r requirements.txt
python main.py                         # http://localhost:8100

# 3) 프론트엔드 (또 다른 터미널)
cd frontend && npm install && npm run dev   # http://localhost:3000
```

| 화면 | 주소 | 누가 보는가 |
|---|---|---|
| 문자 검사 | `/messages` | 어르신 (휴대폰) |
| 분석 결과 · QR | `/result/[id]` | 어르신 (휴대폰) |
| ATM 디스플레이 | `/atm` | ATM 7인치 화면 |
| 상담원 확인 | `/callcenter` | 콜센터 |

시연 계정은 `halmeoni`(사용자) / `callcenter`(상담원)이고, 비밀번호는
`python -m db.seed` 실행 시 출력됩니다.

## 잘 동작하는지 확인하기

```bash
pytest                      # 89 passed 가 나오면 정상 (서버를 안 띄워도 된다)
python scripts/demo_e2e.py  # 백엔드·ATM 데몬을 띄운 상태에서 전 구간 자동 검증
```

## 문서

**[docs/00 문서 체계 및 읽는 순서](./docs/00_문서-체계-및-읽는-순서.md)** 가 나침반입니다.
역할별로 무엇을 먼저 읽어야 하는지 안내합니다.

| | |
|---|---|
| [01 윈도우 개발 핸드북](./docs/01_윈도우-개발-핸드북.md) | 설치 · 테스트 읽는 법 · 코드 수정 · 기능 추가 |
| [02 실행 가이드](./docs/02_스마트금융보안ATM-실행-가이드.md) | 실행 절차 · 라즈베리파이 전환 · 문제 해결 |
| [03 데이터 연동 규격](./docs/03_데이터-연동-규격.md) | API · QR 규격 · DB 스키마 (팀 간 계약서) |
| [04 전시회 시연 매뉴얼](./docs/04_전시회-시연-매뉴얼.md) | **전시 당일에는 이 문서 하나만 본다** |

`AGENTS.md`는 AI에게 이 프로젝트의 규칙을 알려 주는 파일입니다.
`.agents/`의 rules·skills는 이미 완성되어 있으니 다시 만들지 않습니다.

## 기술 스택

FastAPI · SQLAlchemy · MySQL(테스트는 SQLite) · Next.js(TypeScript) ·
OpenCV QR 인식 · gpiozero(라즈베리파이 5)

## 절대 무너뜨리면 안 되는 선

```bash
pytest pi/tests/test_atm_controller.py::test_danger_qr_blocks_withdrawal_and_never_moves_servo
```

이게 빨개지면 **무슨 일이 있어도 커밋하지 않습니다.** 위험 판정에서 현금이 나오지
않는 것이 이 작품의 전부입니다. 배출 판단은 `pi/atm_controller.py`의
`request_withdraw()` **한 곳에만** 둡니다.

그리고 한 가지 더 — **막힌 것은 저절로 풀리지 않습니다.** 기다려도(자동 초기화),
"처음으로"를 눌러도, 다른 QR을 비춰도 풀리지 않습니다. 상담원이 확인해 주거나
은행 직원이 "직원 확인 후 해제"를 눌러야 열립니다. 이 셋 중 하나라도 뚫리면
50만 원 버튼을 누르는 장면이 의미를 잃습니다.
