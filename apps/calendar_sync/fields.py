import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class EncryptedTextField(models.TextField):
    """Encrypt new writes; legacy plaintext remains readable until the next save."""

    prefix = "encrypted:v1:"

    def cipher(self):
        return Fernet(
            base64.urlsafe_b64encode(
                hashlib.sha256(settings.SECRET_KEY.encode()).digest()
            )
        )

    def from_db_value(self, value, expression, connection):
        if value and value.startswith(self.prefix):
            try:
                return (
                    self.cipher().decrypt(value[len(self.prefix) :].encode()).decode()
                )
            except InvalidToken:
                raise ValidationError(
                    "Không thể đọc thông tin Google. Hãy kết nối lại tài khoản."
                )
        return value

    def get_prep_value(self, value):
        if not value:
            return value
        return self.prefix + self.cipher().encrypt(str(value).encode()).decode()
