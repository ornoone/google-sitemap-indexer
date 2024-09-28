from django.db import models

# Create your models here.
SITE_STATUS_CREATED = "CREATED"
SITE_STATUS_PENDING = "PENDING"
SITE_STATUS_OK = "OK"


class TrackedSite(models.Model):
    name = models.CharField(max_length=255, null=False, blank=False)
    sitemap_url = models.URLField(null=False, blank=False)
    status = models.CharField(max_length=255, choices=[
        (SITE_STATUS_CREATED, "created"),
        (SITE_STATUS_PENDING, "pending"),
        (SITE_STATUS_OK, "up to date"),
    ], default=SITE_STATUS_CREATED)

    next_update = models.DateTimeField(null=True, blank=True)
    last_update = models.DateTimeField(null=True, blank=True)

