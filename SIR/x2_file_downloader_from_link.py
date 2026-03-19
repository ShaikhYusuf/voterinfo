import os
import requests
import urllib3
from urllib.parse import quote
from links_pdfs import pdf_links
# Suppress insecure request warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

if __name__ == "__main__":
    base_folder = 'nagpada'
    if not os.path.exists(base_folder):
        os.makedirs(base_folder)

    for url in pdf_links:
        try:
            # 1. Properly encode the URL to handle spaces and special characters
            # We split the URL to avoid encoding the 'https://' part
            base_url = "https://ceoelection.maharashtra.gov.in"
            path = url.replace(base_url, "")
            encoded_url = base_url + quote(path)

            # 2. Clean filename for local storage
            filename = os.path.join(base_folder, url.split('/')[-1].replace(" ", "_").replace(",", ""))
            
            print(f"Downloading: {encoded_url}")
            
            # Adding a User-Agent often helps prevent 403/404 errors on Gov servers
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }

            response = requests.get(encoded_url, headers=headers, timeout=20, verify=False)
            
            if response.status_code == 200:
                with open(filename, 'wb') as f:
                    f.write(response.content)
                print(f"Success: Saved to {filename}")
            else:
                print(f"Server Error: {response.status_code} for {encoded_url}")
                
        except Exception as e:
            print(f"Failed: {e}")