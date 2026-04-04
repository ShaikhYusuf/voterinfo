import os
import requests
from bs4 import BeautifulSoup
from x0_settings import BASE_FOLDER

# base folder
base_folder = BASE_FOLDER
if not os.path.exists(base_folder):
    os.makedirs(base_folder)
    
# --- Part 1: Extract Links ---
with open(f'{base_folder}/link.html', 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f, 'html.parser')

links = [a['href'] for a in soup.find_all('a', href=True) if a['href'].endswith('.pdf')]

links = [f'"https://ceoelection.maharashtra.gov.in/2002/{each_link}"' for each_link in links]

all_links_str = ',\n\t'.join(links)
links_object = f'pdf_links = [\n{all_links_str}\n]'
with open(f'links_pdfs.py', 'w', encoding='utf-8') as f:
    f.write(links_object)