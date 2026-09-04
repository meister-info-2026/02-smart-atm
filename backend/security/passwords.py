"""비밀번호 해싱 (PRD 11.3 보안: Argon2 해시로 저장, 원문은 저장하지 않는다)."""
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

_hasher = PasswordHasher()


def hash_password(plain_password: str) -> str:
    """평문 비밀번호를 Argon2 해시로 변환한다."""
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """평문 비밀번호가 저장된 해시와 일치하는지 확인한다."""
    try:
        return _hasher.verify(password_hash, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
