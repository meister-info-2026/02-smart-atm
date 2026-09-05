# 스마트 금융 보안 ATM — 실행 및 시연 가이드

> 코드를 받은 뒤 처음부터 끝까지 직접 돌려 보는 순서다.
> AI가 만든 코드는 **반드시 직접 실행해서 눈으로 확인한다** (AGENTS.md AI 사용 원칙).
>
> **1차 완성 기준: 윈도우 PC 1대에서 100% 진행한다.** 1~3장과 5장만 하면 전체
> 시스템이 동작한다. 4-2·4-3절(라즈베리파이 5, 7인치 화면)은 **2차 확장**이며
> 1차 완성과 전시회 시연에는 필요하지 않다.
>
> | 이럴 때는 | 이 문서를 본다 |
> |---|---|
> | 실행 절차 전반 · 라즈베리파이 확장(2차) | **이 문서** |
> | 윈도우에 설치·테스트·코드 수정 | `docs/윈도우-개발-핸드북.md` |
> | **작품 전시회 당일 시연** | `docs/전시회-시연-매뉴얼.md` |

---

## 1. 준비 — `.env` 채우기

세 폴더의 `.env.example`을 각각 `.env`로 복사한 뒤 값을 채운다.
`.env`는 커밋되지 않는다 (`.gitignore`).

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
cp pi/.env.example pi/.env
```

반드시 직접 만들어 넣어야 하는 값 두 가지:

```bash
# JWT_SECRET (backend/.env) — 32바이트 이상
python -c "import secrets; print(secrets.token_urlsafe(48))"

# DEVICE_API_KEY (backend/.env와 pi/.env에 같은 값)
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

> 실제 시크릿 값을 AI 채팅에 붙여넣지 않는다. 한 번이라도 붙여넣었다면 노출된 것으로
> 보고 즉시 새로 만든다 (`.agents/rules/security-rules.md`).

---

## 2. 백엔드 (FastAPI + MySQL)

### 2-1. DB 초기화
XAMPP나 MySQL 서버를 켠 뒤 스키마를 만든다.
```bash
mysql -u root -p < backend/db/init.sql
```

### 2-2. 패키지 설치와 시연 데이터
```bash
cd backend
python -m venv venv
# Windows: .\venv\Scripts\Activate.ps1
source venv/bin/activate
pip install -r requirements.txt

python -m db.seed      # 시연용 계정·채팅·문자·장치 생성
```
`seed`가 출력하는 계정으로 로그인한다 (`halmeoni` = 사용자, `callcenter` = 상담원).

### 2-3. 실행
```bash
uvicorn main:app --reload --port 8000
```
확인:
- <http://localhost:8000/health> → `{"data":{"status":"ok", ...}}`
- <http://localhost:8000/health/db> → `{"data":{"status":"ok"}}`
- <http://localhost:8000/docs> → API 목록

> **MySQL이 아직 준비되지 않았다면**, `backend/.env`에
> `DATABASE_URL=sqlite:///./smart_atm.db` 한 줄을 넣으면 SQLite로 바로 돌릴 수 있다.
> 규격은 같으므로 나중에 MySQL로 되돌려도 코드는 바꾸지 않는다.

---

## 3. 프론트엔드 (Next.js)

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
```

| 경로 | 화면 | 누가 보는가 |
|---|---|---|
| `/` | 시작 화면 | 사용자 |
| `/login` | 로그인 | 사용자·상담원 |
| `/messages` | 문자 선택 / 직접 입력 | 사용자 |
| `/result/[id]` | 분석 결과 + QR | 사용자 |
| `/atm` | ATM 7인치 화면 | ATM 디스플레이 |
| `/callcenter` | 상담원 확인 화면 | 콜센터 |

> `NEXT_PUBLIC_API_BASE_URL`의 호스트와 브라우저 주소창의 호스트를 맞춘다.
> 백엔드 `CORS_ORIGINS`에 없는 주소로 접속하면 화면은 뜨는데 데이터만 안 나온다
> (`localhost`와 `127.0.0.1`은 서로 다른 출처로 취급된다).

---

## 4. ATM 제어 데몬

이 프로그램이 QR을 읽고 현금 배출 여부를 판단한다. 폴더 이름이 `pi/`지만
**라즈베리파이가 있어야만 도는 것이 아니다** — 윈도우 PC에서 그대로 돌아간다.

### 4-1. PC에서 실행한다 — 1차 완성은 여기까지다
`DEVICE_MODE=mock`이면 서보모터 없이 로직만 돈다. 실물 장치에 붙이기 전에 반드시
이 단계를 먼저 통과시킨다 (`hardware-rules.md` 안전 수칙 3).
```bash
cd pi
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
`pi/.env`에 `DEVICE_MODE=mock`, `ENABLE_CAMERA=false`를 넣고 실행한다.
```bash
python main.py     # http://localhost:8100
```
카메라 없이 QR 내용을 직접 넣어 볼 수 있다.
```bash
curl -X POST http://localhost:8100/qr \
  -H "Content-Type: application/json" \
  -d '{"data": "{\"session_id\": \"VP-000003\"}"}'
```

### 4-2. (2차 확장 · 선택) 라즈베리파이 5로 옮길 때
```bash
pip install gpiozero lgpio        # Pi 5는 RP1 칩이라 lgpio 핀 팩토리가 필요하다
```
`pi/.env`를 바꾼다.
```
DEVICE_MODE=hardware
GPIOZERO_PIN_FACTORY=lgpio
ENABLE_CAMERA=true
BACKEND_URL=http://<백엔드 PC의 IP>:8000     # localhost는 파이 자신을 뜻한다
SERVO_GATE_PIN=18                            # 조립 후 실제 핀 번호로
SERVO_PUSHER_PIN=19
```
MG996R은 **별도 5V 전원**으로 공급하고 파이는 신호선만 연결한다. 배선 변경은 반드시
전원을 끈 상태에서, 실기기 첫 연결은 교사 입회 하에 진행한다.

### 4-3. (2차 확장 · 선택) 7인치 화면
파이의 브라우저를 키오스크 모드로 `/atm`에 띄운다.
```bash
chromium-browser --kiosk http://<프론트엔드 주소>:3000/atm
```

---

## 5. 자동 검증

### 5-1. 단위·통합 테스트 (서버를 띄우지 않아도 된다)
저장소 루트에서:
```bash
pytest
```
마지막 줄이 `53 passed`이고 `failed`가 없으면 정상이다. 성공·실패 화면을 읽는 방법은
`docs/윈도우-개발-핸드북.md` 3-1절에 자세히 있다.

- `backend/tests/test_rules.py` — TC-01~TC-03, 등급 경계값, CAUTION=VERIFY
- `backend/tests/test_api_flow.py` — 인증 분리, 전체 API 흐름, TC-04·TC-05
- `pi/tests/test_atm_controller.py` — **FR-09**(DANGER에서 배출 장치 미동작), 오프라인 백업
- `pi/tests/test_qr_end_to_end.py` — 실제 QR 이미지를 만들어 다시 읽는 검증
- `pi/tests/test_qr_scanner_backend.py` — PC 웹캠을 켤 때 카메라 백엔드를 고르는 규칙

### 5-2. 통합 시연 검증 (백엔드 + ATM 데몬을 띄운 상태에서)
```bash
python scripts/demo_e2e.py
```
정상 문자 → 출금 가능, 보이스피싱 문자 → 출금 차단 → 콜센터 해제까지 실제 HTTP로
확인하고 결과를 한 줄씩 출력한다.

---

## 6. 발표 시연 순서 (PRD 10장)

> **작품 전시회 시연은 `docs/전시회-시연-매뉴얼.md`를 본다.** 그 문서에는 당일
> 세팅 체크리스트, 장면별 대본과 관람객 설명 멘트, 사고 대응, 인쇄용 요약이 들어 있다.
> 아래는 그 원본이 되는 PRD 10장의 시연 순서 요약이다.

1. **정상 문자** — `/messages`에서 "병원 예약" 문자를 고르고 검사 → **안전**
   → QR 없음, ATM에서 출금 정상 동작
2. **보이스피싱 문자** — "검찰입니다..." 문자를 검사 → **위험 100점**, 근거 4개 표시
   → QR 표시
3. **ATM 인식** — 휴대폰 QR을 ATM 카메라에 보여 준다 → 화면이 빨갛게 바뀌며
   "현금 출금을 잠시 멈췄습니다"
4. **출금 시도** — 50만 원 버튼을 누른다 → **서보가 움직이지 않고** "현금이 나오지
   않습니다" 안내 (이 장면이 이 작품의 핵심이다)
5. **콜센터 확인** — "상담원 확인 요청하기" → `/callcenter` 화면에 세션이 뜬다
   → 문자 내용과 탐지 근거를 확인
6. **분기** — "보이스피싱 — 제한 유지"를 누르면 ATM은 계속 막혀 있고,
   "정상 거래 — 제한 해제"를 누르면 몇 초 뒤 ATM이 출금 가능으로 바뀐다
7. **잘못된 QR** — 아무 QR이나 비춰 본다 → "등록되지 않은 QR입니다" 안내만 뜨고
   거래 제어에는 쓰이지 않는다

### 백업 시연 (네트워크가 끊겼을 때)
- `pi/.env`에 `ENABLE_CAMERA=false`를 두고 `POST /qr`로 진행한다
- 백엔드까지 죽었다면 `{"session_id": "VP-000001", "risk_level": "DANGER"}` 형태의 QR을
  미리 만들어 둔다 — ATM이 로컬 판단으로 차단까지는 시연할 수 있다
  (콜센터 해제는 서버가 필요하다)

---

## 7. 자주 막히는 곳

| 증상 | 원인 · 해결 |
|---|---|
| 화면은 뜨는데 목록이 비어 있다 | CORS. 백엔드 `CORS_ORIGINS`에 브라우저 주소를 정확히 넣는다 |
| 로그인이 계속 401 | `python -m db.seed`를 안 돌렸거나 비밀번호가 다르다. seed 출력 확인 |
| ATM API가 401 | `pi/.env`와 `backend/.env`의 `DEVICE_API_KEY`가 다르다 |
| 파이에서 백엔드에 못 붙는다 | `BACKEND_URL`이 `localhost`로 되어 있다. PC의 실제 IP로 바꾼다 |
| `gpiozero` 오류 | Pi 5는 `lgpio`가 필요하다. `pip install lgpio` 후 `GPIOZERO_PIN_FACTORY=lgpio` |
| 카메라를 못 연다 | `ENABLE_CAMERA=false`로 두고 `POST /qr`로 먼저 로직을 검증한다 |
| QR이 잘 안 읽힌다 | 휴대폰 화면 밝기를 올리고 QR을 크게 표시한다. 초점 거리를 20cm 이상 둔다 |
