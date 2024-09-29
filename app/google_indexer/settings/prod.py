import copy
import os

from .base import *
from .base import INSTALLED_APPS, LOGGING, MIDDLEWARE, REDIS_HOST, REDIS_PORT, HUEY

DEBUG = False

ALLOWED_HOSTS = ["*"]


INSTALLED_APPS = copy.deepcopy(INSTALLED_APPS)



SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"

LOGGING = copy.deepcopy(LOGGING)


HUEY = copy.deepcopy(HUEY)  # noqa: F405
HUEY["immediate"] = False