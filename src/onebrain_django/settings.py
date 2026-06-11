from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]

SECRET_KEY = os.getenv("ONEBRAIN_DJANGO_SECRET_KEY", "onebrain-local-dev-secret")
DEBUG = os.getenv("ONEBRAIN_DJANGO_DEBUG", "false").lower() in {"1", "true", "yes"}
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv(
        "ONEBRAIN_DJANGO_ALLOWED_HOSTS",
        "127.0.0.1,localhost,0.0.0.0,testserver",
    ).split(",")
    if host.strip()
]

ROOT_URLCONF = "onebrain_django.urls"
ASGI_APPLICATION = "onebrain_django.asgi.application"
WSGI_APPLICATION = "onebrain_django.wsgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "rest_framework",
    "onebrain_django.api",
    "onebrain_django.mcp",
    "onebrain_django.web",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.getenv(
            "ONEBRAIN_DJANGO_SQLITE_PATH", str(BASE_DIR / ".onebrain_django.sqlite3")
        ),
    }
}

STATIC_URL = "static/"
DATA_UPLOAD_MAX_MEMORY_SIZE = int(
    os.getenv("ONEBRAIN_DJANGO_DATA_UPLOAD_MAX_MEMORY_SIZE", str(64 * 1024 * 1024))
)
FILE_UPLOAD_MAX_MEMORY_SIZE = DATA_UPLOAD_MAX_MEMORY_SIZE

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "UNAUTHENTICATED_USER": None,
}
