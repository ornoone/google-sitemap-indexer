from django.db import models

# Create your models here.
SITE_STATUS_PENDING = "PENDING"
SITE_STATUS_OK = "OK"
class TrackedWebsite(models.Model):
    name = models.CharField(max_length=255)
    sitemap_url = models.URLField()
    status = models.CharField(max_length=255, choices=[(
        (SITE_STATUS_PENDING, "pending"),
        (SITE_STATUS_OK, "up to date"),
    )])


