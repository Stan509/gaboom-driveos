from pathlib import Path
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file from project root
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"

# Production ALLOWED_HOSTS configuration
if DEBUG:
    # Development hosts
    allowed_hosts_raw = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
    ALLOWED_HOSTS = [h.strip() for h in allowed_hosts_raw.split(",") if h.strip()]
else:
    # Production hosts - include environment variable + defaults
    env_hosts = os.environ.get("DJANGO_ALLOWED_HOSTS", "")
    if env_hosts:
        additional_hosts = [h.strip() for h in env_hosts.split(",") if h.strip()]
    else:
        additional_hosts = []
    
    ALLOWED_HOSTS = [
        "gaboomdriveos.gaboomholding.com",
        "www.gaboomdriveos.gaboomholding.com",
        "64.225.25.34",
        "localhost",
        "127.0.0.1",
    ] + additional_hosts

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "core",
    "agencies",
    "tracking",
    "dashboard",
    "public_site",
    "clients",
    "billing",
    "marketing",
    "superadmin",
    "anymail",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # Add WhiteNoise after SecurityMiddleware
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.SuperAdminOnlyMiddleware",
    "core.middleware.AgencyMiddleware",
    "core.middleware.EmailVerificationMiddleware",
    "core.middleware_access.RequireActiveAccessMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.i18n",
                "core.context_processors.user_permissions",
                "core.context_processors.dashboard_theme",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

use_postgres = bool(os.environ.get("POSTGRES_HOST"))
if use_postgres:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("POSTGRES_DB", "gaboom_driveos"),
            "USER": os.environ.get("POSTGRES_USER", "postgres"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
            "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fr"
LANGUAGES = [
    ("fr", "Français"),
    ("en", "English"),
    ("es", "Español"),
    ("ht", "Kreyòl"),
]
from django.conf.locale import LANG_INFO
LANG_INFO.update({
    "ht": {
        "bidi": False,
        "code": "ht",
        "name": "Haitian Creole",
        "name_local": "Kreyòl",
    }
})
LOCALE_PATHS = [BASE_DIR / "locale"]
LANGUAGE_COOKIE_NAME = "gaboom_lang"
def _compile_po_to_mo(po_path, mo_path):
    import ast
    import struct
    from pathlib import Path

    data = Path(po_path).read_text(encoding="utf-8").splitlines()
    messages = {}
    msgid = None
    msgstr = None
    state = None
    fuzzy = False
    for line in data:
        line = line.strip()
        if line.startswith("#,") and "fuzzy" in line:
            fuzzy = True
        elif line.startswith("msgid"):
            if msgid is not None and msgstr is not None and not fuzzy:
                messages[msgid] = msgstr
            msgid = ast.literal_eval(line[5:].strip() or '""')
            msgstr = ""
            state = "msgid"
            fuzzy = False
        elif line.startswith("msgstr"):
            msgstr = ast.literal_eval(line[6:].strip() or '""')
            state = "msgstr"
        elif line.startswith('"'):
            part = ast.literal_eval(line)
            if state == "msgid":
                msgid += part
            elif state == "msgstr":
                msgstr += part
        elif not line:
            if msgid is not None and msgstr is not None and not fuzzy:
                messages[msgid] = msgstr
            msgid = None
            msgstr = None
            state = None
            fuzzy = False
    if msgid is not None and msgstr is not None and not fuzzy:
        messages[msgid] = msgstr

    keys = sorted(messages.keys())
    ids = b"\x00".join(k.encode("utf-8") for k in keys) + b"\x00"
    strs = b"\x00".join(messages[k].encode("utf-8") for k in keys) + b"\x00"
    n = len(keys)
    o1 = 7 * 4
    o2 = o1 + n * 8
    o3 = o2 + n * 8
    ids_start = o3
    strs_start = o3 + len(ids)
    offsets_ids = []
    offset = 0
    for k in keys:
        b = k.encode("utf-8")
        offsets_ids.append((len(b), ids_start + offset))
        offset += len(b) + 1
    offsets_strs = []
    offset = 0
    for k in keys:
        b = messages[k].encode("utf-8")
        offsets_strs.append((len(b), strs_start + offset))
        offset += len(b) + 1

    output = struct.pack("Iiiiiii", 0x950412de, 0, n, o1, o2, 0, 0)
    for length, off in offsets_ids:
        output += struct.pack("II", length, off)
    for length, off in offsets_strs:
        output += struct.pack("II", length, off)
    output += ids
    output += strs
    Path(mo_path).write_bytes(output)

def _ensure_mo():
    import os
    from pathlib import Path
    for base in LOCALE_PATHS:
        base = Path(base)
        if not base.exists():
            continue
        for po in base.glob("**/LC_MESSAGES/*.po"):
            mo = po.with_suffix(".mo")
            if not mo.exists() or os.path.getmtime(po) > os.path.getmtime(mo):
                _compile_po_to_mo(po, mo)

try:
    _ensure_mo()
except Exception:
    pass
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # 10 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024    # 10 MB
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "core.User"

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/"

# ── Email — Brevo HTTP API (via django-anymail) ─────────────────────
# ⚠ NE JAMAIS hardcoder les clés API ici. Utiliser les variables d'environnement.
# Voir .env.example pour la liste complète des variables requises.
ANYMAIL = {
    "BREVO_API_KEY": os.environ.get("BREVO_API_KEY", ""),
}
EMAIL_BACKEND = "anymail.backends.brevo.EmailBackend"
if DEBUG and not ANYMAIL["BREVO_API_KEY"]:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "gaboom.hti@gmail.com")
SERVER_EMAIL = os.environ.get("SERVER_EMAIL", "gaboom.hti@gmail.com")
ADMINS = [("Stanley", "stanleyMusic2000@gmail.com")]

# ── Validation runtime : clés obligatoires en production ────────────
if not DEBUG:
    _brevo_key = ANYMAIL.get("BREVO_API_KEY", "")
    if not _brevo_key:
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured(
            "BREVO_API_KEY est vide. En production (DEBUG=False), "
            "cette variable d'environnement est obligatoire pour l'envoi d'emails. "
            "Voir .env.example pour la configuration."
        )

# ── Security — production hardening ─────────────────────────────────
# Always set proxy header for Dokku/Nginx compatibility
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000          # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    CSRF_COOKIE_HTTPONLY = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_AGE = 86400              # 24 hours
    SESSION_EXPIRE_AT_BROWSER_CLOSE = False
    
    # Production CSRF trusted origins
    env_origins = os.environ.get("CSRF_TRUSTED_ORIGINS", "")
    if env_origins:
        additional_origins = [o.strip() for o in env_origins.split(",") if o.strip()]
    else:
        additional_origins = []
    
    CSRF_TRUSTED_ORIGINS = [
        "http://gaboomdriveos.gaboomholding.com",
        "https://gaboomdriveos.gaboomholding.com",
        "http://www.gaboomdriveos.gaboomholding.com",
        "https://www.gaboomdriveos.gaboomholding.com",
    ] + additional_origins
else:
    # Development CSRF settings
    CSRF_TRUSTED_ORIGINS = [
        o.strip() for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
    ]

# ── File upload security ────────────────────────────────────────────
ALLOWED_UPLOAD_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".pdf"}
ALLOWED_UPLOAD_MIME_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml",
    "application/pdf",
}

# ── Logging ─────────────────────────────────────────────────────────
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "gaboom.rbac": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
