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
        "*",
    ]


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

    DEBUG_TOOLBAR_CONFIG = {"SHOW_TOOLBAR_CALLBACK": lambda request: True}
