import urllib.parse
from traceback import print_exc

import requests
import xml.etree.ElementTree as ET

from django.db import transaction
from django.db.models import Q, F
from google.oauth2 import service_account

from google_indexer.apps.indexer.exceptions import ApiKeyExpired, ApiKeyInvalid, WebsiteExhausted
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


def page_is_indexed(url, apikey):

    SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
    ENDPOINT = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"

    credentials = service_account.Credentials.from_service_account_info(apikey.content, scopes=SCOPES)
    if not credentials.valid:
        credentials.refresh(Request())
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {credentials.token}"
    }
    parsed = urllib.parse.urlparse(url)
    data = {
        "inspectionUrl": url + "abcd",
        "siteUrl": f'sc-domain:{parsed.netloc}',
        "languageCode": 'fr'
    }
    response = requests.post(ENDPOINT, headers=headers, json=data)
    status_code = response.status_code
    if status_code == 429:
        # {'error': {'code': 429, 'message': 'Quota exceeded for sc-domain:apprendre-une-langue-etrangere.fr.', 'status': 'RESOURCE_EXHAUSTED'}}
        raise WebsiteExhausted()
    if status_code != 200:
        print("error while using key %s to validate %s" % (apikey.name, url))
        print(response.json())
        return False
    ###
    ## result for indexed page
    # {'inspectionResult': {'inspectionResultLink': 'https://search.google.com/search-console/inspect?resource_id=sc-domain:petandzen.fr&id=kVFLlIZalzpUTXztLe7VGw&utm_medium=link&utm_source=api', 'indexStatusResult': {'verdict': 'PASS', 'coverageState': 'Envoyée et indexée', 'robotsTxtState': 'ALLOWED', 'indexingState': 'INDEXING_ALLOWED', 'lastCrawlTime': '2024-10-06T07:09:51Z', 'pageFetchState': 'SUCCESSFUL', 'googleCanonical': 'https://petandzen.fr/garde-a-domicile-chien-chat-nac/ammerschwihr', 'userCanonical': 'https://petandzen.fr/garde-a-domicile-chien-chat-nac/ammerschwihr', 'sitemap': ['https://petandzen.fr/garde.xml', 'https://petandzen.fr/sitemap.xml'], 'referringUrls': ['https://petandzen.fr/garde.xml'], 'crawledAs': 'MOBILE'}, 'mobileUsabilityResult': {'verdict': 'VERDICT_UNSPECIFIED'}, 'richResultsResult': {'verdict': 'PASS', 'detectedItems': [{'richResultType': 'Fils d&#39;Ariane', 'items': [{'name': 'Élément sans nom'}]}, {'richResultType': 'Champ de recherche associé aux liens sitelink', 'items': [{'name': 'Élément sans nom'}]}]}}}

    # result for non indexed page
    # {'inspectionResult': {'inspectionResultLink': 'https://search.google.com/search-console/inspect?resource_id=sc-domain:petandzen.fr&id=tt9FEco9gzA6HcAG_GyhaQ&utm_medium=link&utm_source=api', 'indexStatusResult': {'verdict': 'NEUTRAL', 'coverageState': 'Google ne reconnaît pas cette URL', 'robotsTxtState': 'ROBOTS_TXT_STATE_UNSPECIFIED', 'indexingState': 'INDEXING_STATE_UNSPECIFIED', 'pageFetchState': 'PAGE_FETCH_STATE_UNSPECIFIED'}, 'mobileUsabilityResult': {'verdict': 'VERDICT_UNSPECIFIED'}}}
    response_data = response.json()
    try:
        return response_data['inspectionResult']['indexStatusResult']['verdict'] == 'PASS'
    except KeyError:
        print_exc()
        return False


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
    today = now.date()
    with transaction.atomic():
        available_key = ApiKey.objects.filter(
            usage=usage,
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
