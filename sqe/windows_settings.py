"""Settings for the disposable native-Windows SQE instance."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'local' / 'sqe' / 'windows'
DATABASE = DATA / 'orders.sqlite3'
BASE_URL = 'http://127.0.0.1:18081'

DATA.mkdir(parents=True, exist_ok=True)
os.environ.update(
    PRETIX_CONFIG_FILE='',
    PRETIX_PRETIX_DATADIR=str(DATA),
    PRETIX_PRETIX_URL=BASE_URL,
    PRETIX_PRETIX_ECB_RATES='false',
    PRETIX_PRETIX_PASSWORD_RESET='false',
    PRETIX_DATABASE_BACKEND='sqlite3',
    PRETIX_DATABASE_NAME=str(DATABASE),
)

from pretix.settings import *  # NOQA
from pretix.settings import STATICFILES_DIRS as SOURCE_STATICFILES_DIRS
from pretix.settings import STATIC_ROOT as ASSET_ROOT
from pretix.settings import STORAGES as DEFAULT_STORAGES

ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
DEBUG = True
VITE_DEV_MODE = False
COMPRESS_ENABLED = COMPRESS_OFFLINE = False
EMAIL_BACKEND = EMAIL_CUSTOM_SMTP_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
STORAGES = {**DEFAULT_STORAGES, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
VITE_ASSETS = Path(ASSET_ROOT) / 'vite'
STATICFILES_DIRS = [*SOURCE_STATICFILES_DIRS, ('vite', VITE_ASSETS)] if VITE_ASSETS.is_dir() else SOURCE_STATICFILES_DIRS
