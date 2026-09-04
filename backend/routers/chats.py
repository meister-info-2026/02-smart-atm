"""채팅방/메시지 라우터 — 사용자향 (JWT 필요).

노약자가 받은 의심 문자를 목록에서 '선택'할 수 있게 하는 화면의 데이터 소스다
(PRD 5.1 문자 입력 방식).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api_responses import api_error, ok
from db.database import get_db
from db.models import ChatRoom, ChatRoomMember, Message, User
from schemas.models import ChatRoomResponse, MessageCreateRequest, MessageResponse
from security.jwt_auth import get_current_user

router = APIRouter(prefix="/api/v1/chats", tags=["chats"])

MESSAGE_PAGE_SIZE = 100


def _require_membership(db: Session, chat_id: int, user_id: int) -> ChatRoom:
    """내가 속한 채팅방인지 확인한다. 아니면 404로 존재 자체를 숨긴다."""
    room = db.get(ChatRoom, chat_id)
    member = (
        db.query(ChatRoomMember)
        .filter(ChatRoomMember.chat_room_id == chat_id, ChatRoomMember.user_id == user_id)
        .first()
    )
    if room is None or member is None:
        raise api_error(404, "CHAT_NOT_FOUND", "채팅방을 찾을 수 없습니다.")
    return room


@router.get("")
def list_chats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """내가 참여한 채팅방 목록을 마지막 메시지와 함께 돌려준다."""
    rooms = (
        db.query(ChatRoom)
        .join(ChatRoomMember, ChatRoomMember.chat_room_id == ChatRoom.id)
        .filter(ChatRoomMember.user_id == current_user.id)
        .order_by(ChatRoom.id)
        .all()
    )

    items = []
    for room in rooms:
        last = (
            db.query(Message)
            .filter(Message.chat_room_id == room.id)
            .order_by(Message.sent_at.desc(), Message.id.desc())
            .first()
        )
        items.append(
            ChatRoomResponse(
                id=room.id,
                title=room.title,
                last_message=last.content if last else None,
                last_message_at=last.sent_at if last else None,
            ).model_dump()
        )
    return ok(items)


@router.get("/{chat_id}/messages")
def list_messages(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """채팅방의 메시지를 오래된 순으로 돌려준다."""
    _require_membership(db, chat_id, current_user.id)
    rows = (
        db.query(Message)
        .filter(Message.chat_room_id == chat_id)
        .order_by(Message.sent_at, Message.id)
        .limit(MESSAGE_PAGE_SIZE)
        .all()
    )
    return ok(
        [
            MessageResponse(
                id=m.id,
                chat_room_id=m.chat_room_id,
                sender_label=m.sender_label,
                content=m.content,
                sent_at=m.sent_at,
            ).model_dump()
            for m in rows
        ]
    )


@router.post("/{chat_id}/messages")
def create_message(
    chat_id: int,
    payload: MessageCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """채팅방에 메시지를 추가한다 (받은 문자를 옮겨 적는 용도로도 쓴다)."""
    _require_membership(db, chat_id, current_user.id)
    message = Message(
        chat_room_id=chat_id,
        sender_user_id=current_user.id,
        sender_label=payload.sender_label,
        content=payload.content,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return ok(
        MessageResponse(
            id=message.id,
            chat_room_id=message.chat_room_id,
            sender_label=message.sender_label,
            content=message.content,
            sent_at=message.sent_at,
        ).model_dump()
    )
