import requests
import xml.etree.ElementTree as ET

from django.db import transaction
from django.db.models import Q, F
from django.utils import timezone

from google_indexer.apps.indexer.models import ApiKey


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


def page_is_indexed(url):
    return True


def call_indexation(url, apikey):
    pass

def get_available_apikey(now):
    """
    return an APIKey which have avialable slot for today.
    return None if no key have availability.
    update the availability of the returned key
    :return:
    """
    today = now.date()
    with transaction.atomic():
        available_key = ApiKey.objects.filter(Q(last_usage__date__lt=today) | (Q(last_usage__date=today) & Q(count_of_the_day__lt=F('max_per_day')))).select_for_update().first()
        if available_key:
            if available_key.last_usage.date == today:
                available_key.count_of_the_day += 1
            else:
                available_key.last_usage = today
                available_key.count_of_the_day = 1
        return available_key
