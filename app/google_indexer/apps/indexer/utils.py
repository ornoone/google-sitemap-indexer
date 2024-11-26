from traceback import print_exc
import time
import socket
import requests
import xml.etree.ElementTree as ET
from google.auth.exceptions import TransportError
from requests.exceptions import ConnectionError
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
    
    while True:  # Boucle pour réessayer en cas d'erreur de réseau
        try:
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
            elif status_code == 503:
                print("Service unavailable (503). Mise en pause de 60 secondes avant de réessayer.")
                time.sleep(60)  # Pause de 60 secondes avant de réessayer
            else:
                print("got unknown response")
                print(response.json())
                raise Exception("unknown status code %s" % status_code)
                
        except (socket.gaierror, TransportError, ConnectionError) as e:
            # Gestion des erreurs de connexion ou de résolution DNS
            if isinstance(e, socket.gaierror) or "Temporary failure in name resolution" in str(e) or "[Errno 101] Network is unreachable" in str(e):
                print("Erreur réseau détectée. Mise en pause de 60 secondes avant de réessayer.")
                time.sleep(60)  # Pause de 60 secondes avant de réessayer
            else:
                # Ré-élévation de l'exception si elle n'est pas une erreur de réseau que nous gérons ici
                raise


def get_available_apikey(now, usage) -> ApiKey | None:
    """
    return an APIKey which have avialable slot for today.
    return None if no key have availability.
    update the availability of the returned key
    :return:
    """
    with transaction.atomic():
        available_key = ApiKey.objects.filter(
            status=APIKEY_VALID
        ).filter(
            count_of_the_day__lt=F('max_per_day')
        ).select_for_update().order_by("count_of_the_day", "last_usage").first()
        prev_usage = None
        if available_key:
            prev_usage = available_key.last_usage
            available_key.last_usage = now
            available_key.count_of_the_day += 1
            available_key.save()
        return prev_usage, available_key


def has_available_apikey(now):
    return ApiKey.objects.filter(status=APIKEY_VALID).filter(count_of_the_day__lt=F('max_per_day')).exists()
