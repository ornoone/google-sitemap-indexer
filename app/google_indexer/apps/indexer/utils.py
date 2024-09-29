from random import random

import requests
import xml.etree.ElementTree as ET

from django.db import transaction
from django.db.models import Q, F
from django.utils import timezone
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


import random
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options


def page_is_indexed(url):
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    chrome_options.add_argument('--log-level=3')
    chrome_options.add_argument("--window-size=800,200")  # Taille de la fenêtre

    service = Service()
    driver = webdriver.Chrome(service=service, options=chrome_options)
    search_url = f"https://www.google.com/search?q=site:{url}"
    driver.get(search_url)
    page_source = str(driver.page_source)
    driver.quit()

    # Détection du CAPTCHA dans le contenu de la page
    if "recaptcha" in page_source or "captcha" in page_source:
        raise Exception("Banned chrome driver")

    if "Aucun document ne correspond aux termes de recherche spécifiés" in page_source:
        return False
    else:
        return True


SCOPES = ["https://www.googleapis.com/auth/indexing"]
ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications:publish"
from google.auth.transport.requests import Request


def call_indexation(url, apikey):
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


def get_available_apikey(now) -> ApiKey | None:
    """
    return an APIKey which have avialable slot for today.
    return None if no key have availability.
    update the availability of the returned key
    :return:
    """
    today = now.date()
    with transaction.atomic():
        available_key = ApiKey.objects.filter(
            status=APIKEY_VALID
        ).filter(
            Q(last_usage__date__lt=today) |
            Q(last_usage__date__isnull=True) |
            (
                    Q(last_usage__date=today) &
                    Q(count_of_the_day__lt=F('max_per_day'))
            )
        ).select_for_update().first()
        if available_key:
            if available_key.last_usage is not None and available_key.last_usage.date() == today:
                available_key.last_usage = now
                available_key.count_of_the_day += 1
            else:
                available_key.last_usage = now
                available_key.count_of_the_day = 1
            available_key.save()
        return available_key


def has_available_apikey(now):
    today = now.date()
    return ApiKey.objects.filter(status=APIKEY_VALID).filter(
        Q(last_usage__date__lt=today) | Q(last_usage__date__isnull=True) | (
                    Q(last_usage__date=today) & Q(count_of_the_day__lt=F('max_per_day')))).exists()
