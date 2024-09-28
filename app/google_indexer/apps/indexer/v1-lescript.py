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
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import msvcrt  # Pour attendre qu'une touche soit appuyée sous Windows

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

# Fonction pour vérifier si une URL est indexée et gérer le CAPTCHA (Étape 2)
def is_url_indexed_selenium(url, driver_path, headless=True):
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    chrome_options.add_argument('--log-level=3')
    chrome_options.add_argument("--window-size=800,200")  # Taille de la fenêtre

    service = Service(driver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    search_url = f"https://www.google.com/search?q=site:{url}"
    driver.get(search_url)
    time.sleep(2)

    page_source = driver.page_source

    # Détection du CAPTCHA dans le contenu de la page
    if "recaptcha" in page_source or "captcha" in page_source:
        print(f"\nCAPTCHA détecté pour {url}. Votre IP publique est probablement bloquée.")
        driver.quit()
        print("Changez d'IP, puis appuyez sur une touche pour fermer le script.")
        msvcrt.getch()  # Attend qu'une touche soit appuyée avant de fermer
        sys.exit(1)  # Sortie du script en cas de CAPTCHA détecté

    if "Aucun document ne correspond aux termes de recherche spécifiés" in page_source:
        return (url, False)
    else:
        return (url, True)

    driver.quit()

# Vérifier les URLs non indexées
def verify_links_indexation(input_file, driver_path, output_ko_file):
    with open(input_file, 'r') as file:
        urls = [line.strip() for line in file.readlines()]

    non_indexed_urls = []
    total_urls = len(urls)
    start_time = time.time()

    def worker_function(url, delay):
        time.sleep(delay)  # Décalage de 1 seconde entre chaque worker
        return is_url_indexed_selenium(url, driver_path)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        for i, url in enumerate(urls):
            futures.append(executor.submit(worker_function, url, i))  # Ajout du délai d'une seconde entre chaque worker

        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            url, is_indexed = future.result()
            if not is_indexed:
                non_indexed_urls.append(url)

            elapsed_time = time.time() - start_time
            remaining_time = (elapsed_time / i) * (total_urls - i)
            percentage = (i / total_urls) * 100
            elapsed_time_str = str(datetime.timedelta(seconds=int(elapsed_time)))
            remaining_time_str = str(datetime.timedelta(seconds=int(remaining_time)))

            sys.stdout.write(
                f"\r[Étape 2] Liens vérifiés : {i}/{total_urls} ({percentage:.2f}%)"
                f" | KO: {len(non_indexed_urls)}"
                f" | Temps écoulé : {elapsed_time_str} | Temps restant estimé : {remaining_time_str}"
            )
            sys.stdout.flush()

    with open(output_ko_file, 'w') as file_ko:
        for url in non_indexed_urls:
            file_ko.write(f"{url}\n")

    print(f"\nVérification terminée. Liens KO enregistrés dans {output_ko_file}.")

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

# Fonction principale pour demander l'étape et enchaîner automatiquement
def main():
    print("Choisissez une étape:")
    print("1. Extraction des liens de sitemap")
    print("2. Vérification de l'indexation")
    print("3. Soumission des liens non indexés")
    
    choix = input("Entrez le numéro de l'étape (1, 2 ou 3): ")

    if choix == '1':
        # Étape 1 : Extraction des liens du sitemap
        sitemap_file = os.path.join(BASE_DIR, "sitemapdessiteuxhumana.txt")
        output_file = os.path.join(BASE_DIR, "all_sitemap_links.txt")
        extract_sitemap_links_from_file(sitemap_file, output_file)
        # Enchaîner les étapes suivantes
        choix = '2'

    if choix == '2':
        # Étape 2 : Vérification de l'indexation
        input_file = os.path.join(BASE_DIR, "all_sitemap_links.txt")
        driver_path = r"C:\chromedriver\chromedriver.exe"  # Ajustez le chemin
        output_ko_file = os.path.join(BASE_DIR, "liens_ko_google.txt")
        verify_links_indexation(input_file, driver_path, output_ko_file)
        # Enchaîner avec l'étape 3
        choix = '3'

    if choix == '3':
        # Étape 3 : Soumission des liens non indexés
        input_file = os.path.join(BASE_DIR, "liens_ko_google.txt")
        submit_links_to_google(input_file)
    else:
        print("Choix invalide. Veuillez relancer le script et entrer un numéro valide.")

if __name__ == "__main__":
    main()
