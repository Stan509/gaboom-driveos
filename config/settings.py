from pathlib import Path
import os
import ast
import struct

import dj_database_url
from dotenv import load_dotenv
from django.conf.locale import LANG_INFO

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file from project root
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"

APP_NAME = "Gaboom DriveOS"

# TEMPORAIRE ET VOLONTAIRE :
# on force tous les hosts pour sortir immédiatement du blocage DisallowedHost.
# Quand le domaine sera stable, on remettra une liste stricte.
ALLOWED_HOSTS = ["*"]

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
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
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

# Database
if not DEBUG:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured(
            "DATABASE_URL environment variable is required in production (DEBUG=False). "
            "Dokku provides this automatically when linking a database service."
        )
    DATABASES = {
        "default": dj_database_url.config(default=database_url, conn_max_age=600)
    }
else:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        DATABASES = {
            "default": dj_database_url.config(default=database_url, conn_max_age=600)
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

LANG_INFO.update(
    {
        "ht": {
            "bidi": False,
            "code": "ht",
            "name": "Haitian Creole",
            "name_local": "Kreyòl",
        }
    }
)

LOCALE_PATHS = [BASE_DIR / "locale"]
LANGUAGE_COOKIE_NAME = "gaboom_lang"


def _compile_po_to_mo(po_path, mo_path):
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

    output = struct.pack("Iiiiiii", 0x950412DE, 0, n, o1, o2, 0, 0)
    for length, off in offsets_ids:
        output += struct.pack("II", length, off)
    for length, off in offsets_strs:
        output += struct.pack("II", length, off)
    output += ids
    output += strs

    Path(mo_path).write_bytes(output)


def _ensure_mo():
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

FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "core.User"

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/"

# Email — Brevo HTTP API wrapper
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "no-reply@gaboomdriveos.com")
SERVER_EMAIL = os.environ.get("SERVER_EMAIL", DEFAULT_FROM_EMAIL)
ADMINS = [("Stanley", "stanleyMusic2000@gmail.com")]

EMAIL_VERIFICATION_REQUIRED = (
    (os.environ.get("EMAIL_VERIFICATION_REQUIRED", "1") or "1").strip().lower()
    in {"1", "true", "yes", "y", "on"}
)
EMAIL_FAIL_OPEN = (
    (os.environ.get("EMAIL_FAIL_OPEN", "1") or "1").strip().lower()
    in {"1", "true", "yes", "y", "on"}
)

EMAIL_BACKEND = (
    "django.core.mail.backends.console.EmailBackend"
    if DEBUG
    else "django.core.mail.backends.dummy.EmailBackend"
)

ANYMAIL = {}

# Security
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    CSRF_COOKIE_HTTPONLY = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_AGE = 86400
    SESSION_EXPIRE_AT_BROWSER_CLOSE = False

CSRF_TRUSTED_ORIGINS = [
    "https://gaboomdriveos.com",
    "https://www.gaboomdriveos.com",
]

# File upload security
ALLOWED_UPLOAD_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".pdf"}
ALLOWED_UPLOAD_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/svg+xml",
    "application/pdf",
}

# Logging
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
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}