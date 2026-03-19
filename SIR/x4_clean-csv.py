import pandas as pd
import re
import requests
import json
import time

# ── Load CSV ──────────────────────────────────────────────────
df = pd.read_csv('nagpada\\nagpada_original.csv', encoding='utf-8-sig')

# Rename columns to clean English names
df.columns = ['Filename', 'Page_No', 'Yadi_Bhag_No', 'Content_Marathi']

# ── Clean Filename ────────────────────────────────────────────
df['Filename'] = df['Filename'].str.strip()

# ── Clean Page_No ─────────────────────────────────────────────
df['Page_No'] = pd.to_numeric(df['Page_No'], errors='coerce').fillna(1).astype(int)

# ── Fix Yadi_Bhag_No ─────────────────────────────────────────
# Some entries are missing or incorrect (e.g., 081 has 0010 instead of 0081)
# Derive correct number from filename prefix (first 3 digits)
def derive_bhag_no(filename):
    match = re.match(r'^(\d+)', filename)
    if match:
        return str(int(match.group(1))).zfill(4)
    return None

df['Yadi_Bhag_No_Corrected'] = df['Filename'].apply(derive_bhag_no)
# Use corrected value; original was often wrong/missing
df['Yadi_Bhag_No'] = df['Yadi_Bhag_No_Corrected']
df.drop(columns=['Yadi_Bhag_No_Corrected'], inplace=True)

# ── Clean Content_Marathi ─────────────────────────────────────
JUNK_PATTERNS = [
    r'यादी भागाच्या\s+(हद्दीचा|sera|eater|Bara|Seta|sala|Beta)\s+तपशील\s*',  # header noise variants
    r'यादी भागाच्या\s+तपशील\s*',
    r'मूळ\s+TA[A-Z]+\.?\s*',       # OCR junk: मूळ TART / TARR / HARTER
    r'मूळ\s+गाव\s*/\s*शहर\.?\s*',  # मूळ गाव/शहर
    r'मूळ\s+गाल/\s*शहरे?\.?\s*',   # variant
    r'मूळ\s+ARTE\.?\s*',
    r'मुळ\s+गाव/शहर\s*\.?\s*',
    r'मुळ\s+गाल/\s*शहर[ेे]?\.?\s*',
    r'मुळ\s+TA[A-Z]+\.?\s*',
    r'सजा\s*$',                     # trailing "सजा" (OCR artefact)
    r'\bसजा\b',                      # inline "सजा"
    r'\bGel\b',                      # OCR noise
    r'\bwT\b',                       # OCR noise
    r'\bAST\b',
    r'\bRTE\b',
    r'\bTe\b',
    r'\bfe\b',
    r'\bik\s*/\s*शहर\b',
    r'\bik\b',
    r'Woo\s+गाव/शहर\s*\.?\s*',
    r'सपना\b',                       # stray word
    r'ik\s*/?\w*',
    r'=\s*\(?re\s*\)?',              # = (re  artefact
    r'=\s*\(?Te\s*\)?',
    r'\bLa\)\s*lat\b',               # OCR for "1अ)"
    r'\bLanai\b',                    # OCR for बॅरिस्टर
    r'\bBAAS\b',                     # OCR noise
    r'\baa\b',                       # OCR noise
    r'\bRARES\b',
    r'\bARES\b',
    r'\bHS\b',
    r'\bantl\b',
    r'\bdeat\b',                     # OCR for रोड
    r'_\s*\|',                       # _ |
    r'\|\s*_',
    r'सळ\s+गाव\s+शहर\b',
    r'सळ\s+गाव,\s*शहर\.',
    r'\bसळ\b',
    r'\bSat\b|\bYat\b|\bSait\b|\bSaita\b|\bTat\b|\bOat\b',  # OCR for lane numbers
    r'\bvad\b|\bVad\b|\bWas\b|\bwaite\b',   # OCR noise
    r'\bZayed\b',
    r'\bGel-\d+\b|\bGe-\d+\b',
    r'न\?\s+ब\b',
    r'\bRPT\b|\bPT\b',
    r'"""',
    r'\[\.नं[^ ]*',                  # OCR bracket artefacts
    r'\bsera\b|\beater\b|\bBara\b|\bSeta\b|\bsala\b|\bBeta\b',  # English OCR noise for हद्दीचा
    r'।\s*',                         # Devanagari danda used mid-sentence wrongly
    r'\biz\b',
    r'\bHS\b',
]

def clean_content(text):
    if pd.isna(text):
        return ''
    text = str(text)

    # Remove pipe separators used as line breaks by OCR
    text = text.replace(' | ', ' ').replace('|', ' ')

    # Apply all junk patterns
    for pat in JUNK_PATTERNS:
        text = re.sub(pat, ' ', text, flags=re.IGNORECASE)

    # Fix double commas
    text = re.sub(r',\s*,', ',', text)

    # Fix stray semicolons used instead of commas
    text = re.sub(r';', ',', text)

    # Fix multiple spaces
    text = re.sub(r'  +', ' ', text)

    # Fix space before comma
    text = re.sub(r'\s+,', ',', text)

    # Strip
    text = text.strip().strip(',').strip()

    return text

df['Content_Marathi_Clean'] = df['Content_Marathi'].apply(clean_content)

# ── Build final clean DataFrame ───────────────────────────────
final = df[['Filename', 'Page_No', 'Yadi_Bhag_No', 'Content_Marathi_Clean']].copy()
final.columns = [
    'Filename',
    'Page No.',
    'Yadi Bhag No.',
    'Boundary Description (Marathi)'
]

# Final whitespace cleanup on all string columns
for col in final.columns:
    if final[col].dtype == object:
        final[col] = final[col].str.strip().str.replace(r'  +', ' ', regex=True)

out_path = 'nagpada\\nagpada.csv'
final.to_csv(out_path, index=False, encoding='utf-8-sig')
print(f"\nSaved to: {out_path}")
print(f"Total rows: {len(final)}")
print(final.head(3).to_string())