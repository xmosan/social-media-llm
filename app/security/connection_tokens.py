"""Versioned authenticated encryption for persisted Instagram credentials.

Legacy rows remain readable during the two-phase rollout. The maintenance
command upgrades them after the compatible application has been deployed.
Empty disconnected values stay empty, including SQL comparisons against "".
"""
import base64
import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.types import Text, TypeDecorator

PREFIX = "sabeel:ig:v1:"


def _cipher():
    from app.config import settings
    key = hmac.new(settings.secret_key.encode(), b"sabeel-instagram-storage-v1",
                   hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def open_token(value):
    if not value or not value.startswith(PREFIX):
        return value
    try:
        return _cipher().decrypt(value[len(PREFIX):].encode()).decode()
    except (InvalidToken, ValueError, UnicodeError):
        raise ValueError("Instagram credentials could not be unlocked. Reconnect the account.") from None


def seal_token(value):
    if not value:
        return value
    if value.startswith(PREFIX):
        open_token(value)  # Never accept an invalid envelope as a credential.
        return value
    return PREFIX + _cipher().encrypt(value.encode()).decode()


class EncryptedInstagramToken(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return seal_token(value)

    def process_result_value(self, value, dialect):
        return open_token(value)
