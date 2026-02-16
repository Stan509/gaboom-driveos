"""
EncryptionService — class-based wrapper around Fernet encryption.

Usage:
    from core.security import EncryptionService
    svc = EncryptionService()
    token = svc.encrypt("my secret")
    plain = svc.decrypt(token)

The Fernet key is loaded from settings.FERNET_KEY (which reads os.environ).
If the key is missing, ensure_fernet_key() can auto-generate and persist it.
"""

import os

from cryptography.fernet import Fernet, InvalidToken

from core.crypto import FernetKeyMissing, ensure_fernet_key


class EncryptionService:
    """Encrypt / decrypt strings using Fernet symmetric encryption."""

    def __init__(self):
        self._fernet = None

    def _get_fernet(self) -> Fernet:
        if self._fernet is not None:
            return self._fernet
        key = os.environ.get("FERNET_KEY", "")
        if not key:
            raise FernetKeyMissing(
                "FERNET_KEY non configurée. "
                "Appelez ensure_fernet_key() ou ajoutez-la dans .env."
            )
        self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
        return self._fernet

    def encrypt(self, value: str) -> str:
        """Encrypt a plaintext string. Returns base64-encoded Fernet token."""
        if not value:
            return ""
        return self._get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt(self, value: str) -> str:
        """Decrypt a Fernet token back to plaintext string."""
        if not value:
            return ""
        try:
            return self._get_fernet().decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            raise ValueError("Impossible de déchiffrer — clé invalide ou données corrompues.")

    @staticmethod
    def is_configured() -> bool:
        """Check whether FERNET_KEY is available."""
        return bool(os.environ.get("FERNET_KEY", ""))

    @staticmethod
    def ensure_key() -> str:
        """Auto-generate FERNET_KEY if missing and persist to .env."""
        return ensure_fernet_key()
