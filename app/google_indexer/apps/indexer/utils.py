import urllib.parse
from traceback import print_exc

import requests
import datetime
import xml.etree.ElementTree as ET

from django.db import transaction
from django.utils import timezone
from django.db.models import Q, F
from google.oauth2 import service_account

from google_indexer.apps.indexer.exceptions import ApiKeyExpired, ApiKeyInvalid
from google_indexer.apps.indexer.models import ApiKey, APIKEY_VALID


# Fonction pour extraire les liens d'un sitemap (Étape 1)
def fetch_sitemap_links(sitemap_url):
    print(f"Fetching sitemap: {sitemap_url}")
    response = requests.get(sitemap_url)
    if response.status_code != 200:
        print(f"Erreur de récupération du sitemap {sitemap_url} : {response.status_code}")
        return []

    root = ET.fromstring(response.content)
    namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    urls = []

    sitemap_elements = root.findall(".//ns:sitemap", namespaces=namespace)
    if sitemap_elements:
        print(f"Sitemap imbriqué détecté dans {sitemap_url}, exploration des sitemaps imbriqués...")
        for sitemap in sitemap_elements:
            loc = sitemap.find('ns:loc', namespaces=namespace).text
            urls.extend(fetch_sitemap_links(loc))  # Appel récursif pour les sitemaps imbriqués
    else:
        print(f"Sitemap simple détecté dans {sitemap_url}")
        urls = [url.text for url in root.findall(".//ns:loc", namespaces=namespace)]

    return urls


from google.auth.transport.requests import Request


def call_indexation(url, apikey):

    SCOPES = ["https://www.googleapis.com/auth/indexing"]
    ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications:publish"
    credentials = service_account.Credentials.from_service_account_info(apikey.content, scopes=SCOPES)
    if not credentials.valid:
        credentials.refresh(Request())
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {credentials.token}"
    }
    data = {
        "url": url,
        "type": "URL_UPDATED"
    }
    response = requests.post(ENDPOINT, headers=headers, json=data)
    status_code = response.status_code
    if status_code == 200:
        return True
    elif status_code == 429:
        raise ApiKeyExpired()
    elif status_code == 403:
        raise ApiKeyInvalid()
    else:
        print("got unknown response")
        print(response.json())
        raise Exception("unkwonn status code %s" % status_code)


def get_available_apikey(now, usage) -> ApiKey | None:
    """
    return an APIKey which have avialable slot for today.
    return None if no key have availability.
    update the availability of the returned key
    :return:
    """
    begin_of_today = timezone.make_aware(datetime.datetime.combine(now.date(), datetime.time(hour=9, minute=0, second=0)))
    with transaction.atomic():
        available_key = ApiKey.objects.filter(
            usage=usage,
            status=APIKEY_VALID
        ).filter(
            Q(last_usage__lt=begin_of_today) |
            Q(last_usage__isnull=True) |
            (
                    Q(last_usage__gte=begin_of_today) &
                    Q(count_of_the_day__lt=F('max_per_day'))
            )
        ).select_for_update().order_by("count_of_the_day", "last_usage").first()
        prev_usage = None
        if available_key:
            prev_usage = available_key.last_usage
            if available_key.last_usage is not None and available_key.last_usage >= begin_of_today:
                available_key.last_usage = now
                available_key.count_of_the_day += 1
            else:
                available_key.last_usage = now
                available_key.count_of_the_day = 1
            available_key.save()
        return prev_usage, available_key


def has_available_apikey(now):
    begin_of_today = timezone.make_aware(datetime.datetime.combine(now.date(), datetime.time(hour=9, minute=0, second=0)))

    return ApiKey.objects.filter(status=APIKEY_VALID).filter(
        Q(last_usage__lt=begin_of_today) | Q(last_usage__isnull=True) | (
                    Q(last_usage__gte=begin_of_today) & Q(count_of_the_day__lt=F('max_per_day')))).exists()
