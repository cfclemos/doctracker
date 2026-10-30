"""Settings of the acme example: only the shop app, on the database ACME_DATABASE (an SQLite file by default)."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = "only-for-the-example"
INSTALLED_APPS = ["shop"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": os.environ.get("ACME_DATABASE", BASE_DIR / "acme.sqlite")}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
