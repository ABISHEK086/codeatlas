from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from .config import settings

_fernet = Fernet(settings.token_encryption_key.encode()) if settings.token_encryption_key else None

PREFIX = "enc:"  # marks encrypted values so plain-text legacy rows are recognised


class EncryptedText(TypeDecorator):
    """Encrypts on write, decrypts on read. Transparent to the rest of the code."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None or _fernet is None:
            return value
        return PREFIX + _fernet.encrypt(value.encode()).decode()

    def process_result_value(self, value, dialect):
        if value is None or not value.startswith(PREFIX):
            return value  # legacy plain text, or encryption disabled
        if _fernet is None:
            return None   # encrypted data but no key available
        try:
            return _fernet.decrypt(value[len(PREFIX):].encode()).decode()
        except InvalidToken:
            return None   # wrong key: treat as no token, user signs in again