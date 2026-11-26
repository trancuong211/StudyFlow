import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

_SALT = b'studyflow-ai-config-v1'


def _get_fernet():
    digest = hashlib.sha256(settings.SECRET_KEY.encode('utf-8') + _SALT).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value):
    """Mã hóa một chuỗi bí mật (API key) để lưu vào database."""
    return _get_fernet().encrypt(value.encode('utf-8')).decode('utf-8')


def decrypt_secret(token):
    """Giải mã API key đã lưu. Trả về chuỗi rỗng nếu không giải mã được."""
    if not token:
        return ''
    try:
        return _get_fernet().decrypt(token.encode('utf-8')).decode('utf-8')
    except (InvalidToken, ValueError):
        return ''
