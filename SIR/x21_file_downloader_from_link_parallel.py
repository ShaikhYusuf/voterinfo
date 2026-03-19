import os
import requests
import urllib3
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed
from links_pdfs import pdf_links

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://ceoelection.maharashtra.gov.in"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def download_pdf(url, base_folder):
    try:
        path = url.replace(BASE_URL, "")
        encoded_url = BASE_URL + quote(path)
        filename = os.path.join(base_folder, url.split('/')[-1].replace(" ", "_").replace(",", ""))

        print(f"Downloading: {encoded_url}")
        response = requests.get(encoded_url, headers=HEADERS, timeout=20, verify=False)
        if response.status_code == 200:
            with open(filename, 'wb') as f:
                f.write(response.content)
            print(f"Success: Saved to {filename}")
        else:
            print(f"Server Error: {response.status_code} for {encoded_url}")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    base_folder = 'bhiwandi'
    os.makedirs(base_folder, exist_ok=True)

    max_workers = 10

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(download_pdf, url, base_folder) for url in pdf_links]
        for future in as_completed(futures):
            future.result()