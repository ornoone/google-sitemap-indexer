import copy
import os

from .base import *
from .base import INSTALLED_APPS, LOGGING, MIDDLEWARE, REDIS_HOST, REDIS_PORT

DEBUG = True

ALLOWED_HOSTS = ["*"]


INSTALLED_APPS = copy.deepcopy(INSTALLED_APPS)



SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"

if True:
    # enable django debug toolbar
    # to use it, go to http://localhost:8000/b/django-debug-toolbar
    INSTALLED_APPS.append("debug_toolbar")

    MIDDLEWARE = copy.deepcopy(MIDDLEWARE)
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")
    INTERNAL_IPS = [
        "127.0.0.1",
    ]

    DEBUG_TOOLBAR_PANELS = [
        "debug_toolbar.panels.history.HistoryPanel",
        "debug_toolbar.panels.versions.VersionsPanel",
        "debug_toolbar.panels.timer.TimerPanel",
        "debug_toolbar.panels.settings.SettingsPanel",
        "debug_toolbar.panels.headers.HeadersPanel",
        "debug_toolbar.panels.request.RequestPanel",
        "debug_toolbar.panels.sql.SQLPanel",
        "debug_toolbar.panels.cache.CachePanel",
        "debug_toolbar.panels.signals.SignalsPanel",
        "debug_toolbar.panels.logging.LoggingPanel",
    ]
    DEBUG_TOOLBAR_CONFIG = {
        "RENDER_PANELS": False,
    }

LOGGING = copy.deepcopy(LOGGING)

for logger in (
    # "exagere.apps.stock.rpc",
    "exagere",
):
    LOGGING["loggers"][logger] = {
        "handlers": ["console"],
        "level": "DEBUG",
        "propagate": False,
    }
