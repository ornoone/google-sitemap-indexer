import os
import requests
import xml.etree.ElementTree as ET
import concurrent.futures
import time
import sys
import datetime
import json
from google.oauth2 import service_account
from google.auth.transport.requests import Request


# Variables pour la soumission à l'API Google
SCOPES = ["https://www.googleapis.com/auth/indexing"]
ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications:publish"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLEFS_FOLDER = os.path.join(BASE_DIR, "clef")
PAS_DE_SLOT_FILE = os.path.join(BASE_DIR, "pas_de_slot.txt")
ERREUR_INDEXATION_FILE = os.path.join(BASE_DIR, "erreur_indexation.txt")
CLE_ET_DOMAINE_FILE = os.path.join(BASE_DIR, "cleetdomaine.txt")
LIENS_KO_FILE = os.path.join(BASE_DIR, "liens_ko_google.txt")
URLS_PER_KEY = 200  # Nombre maximal d'URL par clé

# Fonction de chargement des informations d'identification
def authenticate_with_google(credentials_json_path):
    credentials = service_account.Credentials.from_service_account_file(credentials_json_path, scopes=SCOPES)
    return credentials

# Fonction pour envoyer la requête de soumission d'URL à Google
def submit_url_to_google(url, credentials):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {credentials.token}"
    }
    data = {
        "url": url,
        "type": "URL_UPDATED"
    }
    response = requests.post(ENDPOINT, headers=headers, json=data)
    return response.status_code, response.json()

# Fonction pour rafraîchir les jetons d'authentification si nécessaire
def refresh_token_if_needed(credentials):
    if not credentials.valid:
        credentials.refresh(Request())

# Lecture des URLs à partir d'un fichier
def read_urls_from_file(file_path):
    with open(file_path, "r") as file:
        urls = file.readlines()
    return [url.strip() for url in urls]

# Écrire les URLs non soumises dans un fichier
def write_urls_to_file(urls, file_path):
    with open(file_path, "a") as file:
        for url in urls:
            file.write(f"{url}\n")

# Écrire le fichier de clé et domaine pour les erreurs 403
def write_cle_et_domaine(url, json_file):
    with open(CLE_ET_DOMAINE_FILE, "a") as file:
        file.write(f"URL: {url} - Clé: {json_file}\n")

# Lister les fichiers JSON dans le dossier des clés
def list_json_files(folder_path):
    return [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.endswith(".json")]

# Fonction pour afficher la progression des soumissions
def print_progress_submissions(total_urls, submitted_success, submitted_error, remaining_urls, start_time, current_key):
    elapsed_time = time.time() - start_time
    percentage = (submitted_success / total_urls) * 100
    remaining_time = ((elapsed_time / submitted_success) * (total_urls - submitted_success)) if submitted_success > 0 else 0
    elapsed_time_str = str(datetime.timedelta(seconds=int(elapsed_time)))
    remaining_time_str = str(datetime.timedelta(seconds=int(remaining_time)))

    sys.stdout.write(
        f"\r[Soumission] Liens soumis : {submitted_success}/{total_urls} ({percentage:.2f}%) | Échecs : {submitted_error} | URLs restantes : {len(remaining_urls)} | Clé : {current_key}\n"
        f"Temps écoulé : {elapsed_time_str} | Temps restant estimé : {remaining_time_str}"
    )
    sys.stdout.flush()

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

# Fonction pour extraire les liens à partir d'un fichier de sitemaps et les écrire dans un fichier
def extract_sitemap_links_from_file(sitemap_file, output_file):
    with open(sitemap_file, 'r') as file:
        sitemap_urls = [line.strip() for line in file.readlines()]

    if not sitemap_urls:
        print("Aucune URL de sitemap trouvée dans le fichier.")
        return

    all_links = []
    start_time = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(fetch_sitemap_links, url) for url in sitemap_urls]
        total_links = len(sitemap_urls)

        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            result = future.result()
            if not result:
                print(f"Aucun lien trouvé dans le sitemap {sitemap_urls[i-1]}")
            all_links.extend(result)

            elapsed_time = time.time() - start_time
            remaining_time = (elapsed_time / i) * (total_links - i)
            percentage = (i / total_links) * 100
            elapsed_time_str = str(datetime.timedelta(seconds=int(elapsed_time)))
            remaining_time_str = str(datetime.timedelta(seconds=int(remaining_time)))

            sys.stdout.write(
                f"\r[Étape 1] Liens extraits : {i}/{total_links} ({percentage:.2f}%)"
                f" | Temps écoulé : {elapsed_time_str} | Temps restant estimé : {remaining_time_str}"
            )
            sys.stdout.flush()

    if not all_links:
        print("\nAucun lien n'a été extrait de tous les sitemaps.")

    with open(output_file, 'w') as file:
        for link in all_links:
            file.write(link + '\n')

    print(f"\nExtraction complète. Liens enregistrés dans {output_file}.")


# Soumission des liens non indexés (KO) à Google avec rotation des clés JSON (Étape 3)
def submit_links_to_google(input_file):
    with open(input_file, 'r') as file:
        urls = [line.strip() for line in file.readlines()]

    json_files = [os.path.join(CLEFS_FOLDER, f) for f in os.listdir(CLEFS_FOLDER) if f.endswith(".json")]
    if not json_files:
        print("Aucune clé JSON trouvée.")
        return

    total_urls = len(urls)
    remaining_urls = urls[:]
    submitted_success = 0
    submitted_error = 0

    start_time = time.time()

    for json_file in json_files:
        if not remaining_urls:
            break

        credentials = authenticate_with_google(json_file)
        remaining_slots = URLS_PER_KEY
        current_key = os.path.basename(json_file)

        while remaining_slots > 0 and remaining_urls:
            refresh_token_if_needed(credentials)
            url = remaining_urls.pop(0)

            status_code, response = submit_url_to_google(url, credentials)

            if status_code == 200:
                submitted_success += 1
                remaining_slots -= 1
            elif status_code == 429:
                print(f"\nQuota épuisé pour la clé : {json_file}. Passage à la clé suivante.")
                remaining_urls.insert(0, url)
                break
            elif status_code == 403:
                print(f"\nErreur de permission pour {url} avec la clé {json_file}")
                write_cle_et_domaine(url, json_file)
                remaining_urls.insert(0, url)
                break
            else:
                print(f"\nErreur lors de la soumission de {url}: {response}")
                write_urls_to_file([url], ERREUR_INDEXATION_FILE)
                submitted_error += 1

            print_progress_submissions(total_urls, submitted_success, submitted_error, remaining_urls, start_time, current_key)

    if remaining_urls:
        write_urls_to_file(remaining_urls, PAS_DE_SLOT_FILE)
        print(f"\n{len(remaining_urls)} URLs non soumises par manque de slots. Voir {PAS_DE_SLOT_FILE}.")

