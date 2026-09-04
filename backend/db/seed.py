"""시연용 seed 데이터 생성 스크립트.

실행: (backend 폴더에서) python -m db.seed
재실행해도 중복이 생기지 않도록 이미 있으면 건너뛴다.

PRD 5.9: 테스트용 계정·채팅·분석 데이터는 시연을 위해 seed 스크립트로 재생성할 수 있다.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session

from db.database import SessionLocal, init_db
from db.models import (
    ROLE_AGENT,
    ROLE_USER,
    ChatRoom,
    ChatRoomMember,
    Device,
    Friendship,
    Message,
    User,
)
from security.passwords import hash_password

# 시연 계정 비밀번호는 .env로 바꿀 수 있다 (실제 배포에서는 반드시 바꾼다)
DEFAULT_SEED_PASSWORD = "demo1234"

DEMO_USERS = [
    ("halmeoni", "김순자 (사용자)", ROLE_USER),
    ("callcenter", "박상담 (콜센터 상담원)", ROLE_AGENT),
    ("friend01", "이영희 (딸)", ROLE_USER),
]

# 시연용 문자 3종 — PRD 10장 대표 시연 시나리오와 같은 문장을 쓴다
DEMO_CHATS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "010-2345-6789 (딸)",
        [
            ("이영희 (딸)", "엄마, 오늘 오후 3시에 병원 예약이 있습니다. 잊지 마세요."),
            ("이영희 (딸)", "끝나면 전화 주세요."),
        ],
    ),
    (
        "02-500-0000 (모르는 번호)",
        [
            (
                "모르는 번호",
                "검찰입니다. 계좌가 범죄에 연루되었습니다. "
                "현금 500만 원을 인출해 지정 장소로 가져오세요.",
            ),
        ],
    ),
    (
        "010-9999-1234 (모르는 번호)",
        [
            (
                "모르는 번호",
                "은행 직원이나 가족에게 말하지 마시고 지금 바로 돈을 찾아오세요.",
            ),
        ],
    ),
]

# AGENTS.md '팀 정보' 표의 제어 대상 (db-integration 스킬: devices 시드)
DEMO_DEVICES = [
    ("cash_dispenser_1", "현금 배출 시연 장치 (MG996R x2)", "cash_dispenser"),
    ("qr_scanner_1", "QR 인식 카메라", "qr_scanner"),
    ("buzzer_1", "경고 부저 (선택)", "buzzer"),
]


def _get_or_create_user(
    db: Session, username: str, display_name: str, role: str, password: str
) -> User:
    user = db.query(User).filter(User.username == username).first()
    if user:
        return user
    user = User(
        username=username,
        display_name=display_name,
        role=role,
        password_hash=hash_password(password),
    )
    db.add(user)
    db.flush()
    return user


def seed() -> None:
    """시연 데이터를 만든다."""
    init_db()
    password = os.getenv("SEED_DEFAULT_PASSWORD", DEFAULT_SEED_PASSWORD)

    with SessionLocal() as db:
        users = {
            username: _get_or_create_user(db, username, display_name, role, password)
            for username, display_name, role in DEMO_USERS
        }
        owner = users["halmeoni"]
        friend = users["friend01"]

        if not db.query(Friendship).filter(Friendship.user_id == owner.id).first():
            db.add(Friendship(user_id=owner.id, friend_user_id=friend.id))
            db.add(Friendship(user_id=friend.id, friend_user_id=owner.id))

        for title, messages in DEMO_CHATS:
            room = db.query(ChatRoom).filter(ChatRoom.title == title).first()
            if room:
                continue
            room = ChatRoom(title=title)
            db.add(room)
            db.flush()
            db.add(ChatRoomMember(chat_room_id=room.id, user_id=owner.id))
            for sender_label, content in messages:
                db.add(
                    Message(
                        chat_room_id=room.id,
                        sender_user_id=None,
                        sender_label=sender_label,
                        content=content,
                    )
                )

        for device_id, name, kind in DEMO_DEVICES:
            if db.get(Device, device_id) is None:
                db.add(Device(id=device_id, name=name, kind=kind))

        db.commit()

    print("시연 데이터 생성 완료")
    print(f"  사용자 계정   : halmeoni / {password}")
    print(f"  상담원 계정   : callcenter / {password}  (role=agent)")
    print("  채팅방 3개(정상 문자 1, 보이스피싱 문자 2)와 장치 3개를 등록했습니다.")
    if password == DEFAULT_SEED_PASSWORD:
        print("  [주의] 기본 비밀번호를 쓰고 있습니다. .env의 SEED_DEFAULT_PASSWORD로 바꾸세요.")


if __name__ == "__main__":
    seed()
