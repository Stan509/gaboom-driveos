"""
Fernet-based encryption for sensitive platform settings.

The master key FERNET_KEY is loaded from .env / environment variables.
If missing, it can be auto-generated via ensure_fernet_key().

Manual generation:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

_fernet_instance = None


class FernetKeyMissing(Exception):
    """Raised when FERNET_KEY is not configured in the environment."""
    pass


def _env_file_path() -> Path:
    """Return the path to the project .env file."""
    try:
        from django.conf import settings as django_settings
        return Path(django_settings.BASE_DIR) / ".env"
    except Exception:
        # Fallback: assume .env is next to this file's parent (project root)
        return Path(__file__).resolve().parent.parent / ".env"


def ensure_fernet_key() -> str:
    """
    Ensure FERNET_KEY exists in the environment.
    If missing, generate one and append it to .env.
    Returns the key string.
    """
    global _fernet_instance

    key = os.environ.get("FERNET_KEY", "")
    if key:
        return key

    # Generate a new key
    key = Fernet.generate_key().decode()
    os.environ["FERNET_KEY"] = key
    _fernet_instance = None  # reset cache

    # Persist to .env
    env_path = _env_file_path()
    try:
        existing = ""
        if env_path.exists():
            existing = env_path.read_text(encoding="utf-8")
        separator = "" if not existing or existing.endswith("\n") else "\n"
        with open(env_path, "a", encoding="utf-8") as f:
            f.write(f"{separator}FERNET_KEY={key}\n")
        logger.info("FERNET_KEY auto-generated and saved to %s", env_path)
    except OSError:
        logger.warning(
            "FERNET_KEY auto-generated but could not write to %s. "
            "Add manually: FERNET_KEY=%s", env_path, key,
        )

    return key


def get_fernet():
    """Return a cached Fernet instance using FERNET_KEY from env."""
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance

    key = os.environ.get("FERNET_KEY", "")
    if not key:
        raise FernetKeyMissing(
            "FERNET_KEY manquant dans les variables d'environnement. "
            "Générez-en une avec: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )

    _fernet_instance = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet_instance


def encrypt(plaintext: str) -> str:
    """Encrypt a plaintext string, return base64-encoded token."""
    if not plaintext:
        return ""
    f = get_fernet()
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    """Decrypt a Fernet token back to plaintext string."""
    if not token:
        return ""
    f = get_fernet()
    return f.decrypt(token.encode("utf-8")).decode("utf-8")


def is_fernet_configured() -> bool:
    """Check if FERNET_KEY is available in the environment."""
    return bool(os.environ.get("FERNET_KEY", ""))
