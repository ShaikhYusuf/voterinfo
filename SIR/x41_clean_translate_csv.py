import pandas as pd
import re
import requests
import json
import time

# ── Load CSV ──────────────────────────────────────────────────
df = pd.read_csv('nagpada/nagpada.mar.csv', encoding='utf-8-sig')
df.columns = ['Filename', 'Page_No', 'Yadi_Bhag_No', 'Content_Marathi']

df['Page_No'] = pd.to_numeric(df['Page_No'], errors='coerce').fillna(1).astype(int)

def derive_bhag_no(filename):
    match = re.match(r'^(\d+)', str(filename).strip())
    return str(int(match.group(1))).zfill(4) if match else ''

df['Yadi_Bhag_No'] = df['Filename'].apply(derive_bhag_no)

JUNK = [
    r'यादी भागाच्या\s+(?:हद्दीचा|sera|eater|Bara|Seta|sala|Beta|eater)\s+तपशील\s*',
    r'यादी भागाच्या\s+तपशील\s*',
    r'मूळ\s+TA[A-Z]+\.?\s*',
    r'मूळ\s+(?:गाव|गाल)\s*/\s*शहर[े]?\.?\s*',
    r'मुळ\s+(?:गाव|गाल)\s*/\s*शहर[े]?\.?\s*',
    r'मूळ\s+ARTE\.?\s*',
    r'मुळ\s+TA[A-Z]+\.?\s*',
    r'\bसजा\b',
    r'\bGel\b|\bGe-\d+\b|\bGel-\d+\b',
    r'\bwT\b|\bAST\b|\bRTE\b|\bik\b|\biz\b|\bHS\b|\bantl\b|\bdeat\b|\bLanai\b|\bBAAS\b|\baa\b|\bARES\b|\bRARES\b',
    r'\bSat\b|\bYat\b|\bSait\b|\bTat\b|\bOat\b|\bvad\b|\bVad\b|\bWas\b|\bwaite\b|\bZayed\b|\bWoo\b',
    r'सळ\s*गाव[\s/]*शहर\.?\s*',
    r'\bसळ\b',
    r'सपना\b',
    r'=\s*\(?(?:re|Te|RTE)\s*\)?',
    r'\bLa\)\s*lat\b',
    r'न\?\s+ब\b',
    r'"""',
    r'\[\.नं[^\s,]*',
    r'।\s*',
    r'_\s*\||\|\s*_',
    r'\|\s*',
    r'\|',
    r'Woo\s+गाव/शहर\.?\s*',
    r'm\s*;\s*',
    r'\bik\s*/\s*शहर\b',
    r'\.\.\.',
    r'\s*\.\.\s*',
]

def clean_content(text):
    if pd.isna(text):
        return ''
    text = str(text)
    for pat in JUNK:
        text = re.sub(pat, ' ', text, flags=re.IGNORECASE)
    text = re.sub(r',\s*,+', ',', text)
    text = re.sub(r';', ',', text)
    text = re.sub(r'\s{2,}', ' ', text)
    text = re.sub(r'\s+,', ',', text)
    text = re.sub(r',\s*$', '', text)
    return text.strip()

df['Content_Marathi_Clean'] = df['Content_Marathi'].apply(clean_content)

# ── Ollama config ─────────────────────────────────────────────
OLLAMA_URL  = "http://localhost:11434/api/generate"
MODEL       = "ministral-3:3b-instruct-2512-q4_K_M"
BATCH_SIZE  = 5          # keep small — 3b model has a limited context window
TIMEOUT     = 180        # seconds per request (increase if your machine is slow)

def check_ollama():
    """Verify Ollama is running and the model is available before starting."""
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        r.raise_for_status()
        models = [m['name'] for m in r.json().get('models', [])]
        if not any(MODEL in m for m in models):
            print(f"⚠️  Model '{MODEL}' not found in Ollama.")
            print(f"   Run:  ollama pull {MODEL}")
            print(f"   Available models: {models}")
            return False
        print(f"✅ Ollama is running. Model '{MODEL}' is ready.")
        return True
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to Ollama at http://localhost:11434")
        print("   Make sure Ollama is running:  ollama serve")
        return False

def translate_batch(texts, retries=3):
    numbered = "\n".join([f"{i+1}. {t}" for i, t in enumerate(texts)])
    prompt = f"""You are a precise translator for Indian municipal/electoral documents.
Translate each numbered Marathi address description to English.
Rules:
- Keep all house/municipal numbers exactly as-is (e.g., म्यु.घ.नं. → Mun. H. No.)
- Keep ward codes like (मनिवि-20) → (MuniWard-20), (म.नि.वि.20) → (MuniWard-20)
- Keep खंड → Block, गल्ली → Lane, मार्ग → Road/Marg, रोड → Road
- Keep section labels: अ) → a), ब) → b), क) → c), ड) → d), इ) → e), फ) → f)
- Keep section numbers: 1, 2, 3, etc.
- Do NOT add any extra explanation.
- Return ONLY a JSON array of strings in the same order, e.g. ["translation1", "translation2"]

{numbered}"""

    for attempt in range(retries):
        try:
            resp = requests.post(
                OLLAMA_URL,
                json={
                    "model": MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 4000,
                        "num_ctx": 8192,       # explicit context window for the q4 model
                    }
                },
                timeout=TIMEOUT
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "").strip()

            # Strip markdown fences if the model wrapped output in ```json ... ```
            raw = re.sub(r'^```json\s*|^```\s*|```$', '', raw, flags=re.MULTILINE).strip()

            # Extract the JSON array even if buried in surrounding text
            match = re.search(r'\[.*?\]', raw, re.DOTALL)
            if match:
                raw = match.group(0)

            translations = json.loads(raw)

            if isinstance(translations, list) and len(translations) == len(texts):
                return translations

            print(f"\n  ⚠️  Got {len(translations)} items for {len(texts)} inputs — retrying...")

        except requests.exceptions.Timeout:
            print(f"\n  ⏱️  Timeout on attempt {attempt+1}/{retries} — model may be slow, retrying...")
            time.sleep(5)
        except json.JSONDecodeError as e:
            print(f"\n  ❌ JSON parse error on attempt {attempt+1}: {e}")
            print(f"     Raw output was: {raw[:300]!r}")
            time.sleep(2)
        except Exception as e:
            print(f"\n  ❌ Attempt {attempt+1} failed: {e}")
            time.sleep(2)

    # Fall back: return each row individually translated (slower but safer)
    print(f"\n  🔁 Falling back to single-row translation for this batch...")
    results = []
    for text in texts:
        single = translate_batch([text], retries=2)
        results.extend(single)
    return results

# ── Main ──────────────────────────────────────────────────────
if not check_ollama():
    raise SystemExit(1)

all_translations = []
rows = df['Content_Marathi_Clean'].tolist()
total_batches = (len(rows) - 1) // BATCH_SIZE + 1

print(f"\nTranslating {len(rows)} rows via Ollama ({MODEL}), batch size {BATCH_SIZE} ...\n")

for i in range(0, len(rows), BATCH_SIZE):
    batch = rows[i:i+BATCH_SIZE]
    batch_num = i // BATCH_SIZE + 1
    print(f"  Batch {batch_num:>4}/{total_batches} ...", end=' ', flush=True)
    translations = translate_batch(batch)
    all_translations.extend(translations)
    print("✓")

df['Content_English'] = all_translations

# ── Save output ───────────────────────────────────────────────
final = df[['Filename', 'Page_No', 'Yadi_Bhag_No', 'Content_English']].copy()
final.columns = [
    'Filename',
    'Page No.',
    'Yadi Bhag No.',
    'Boundary Description (English)'
]

for col in final.columns:
    if final[col].dtype == object:
        final[col] = final[col].str.strip().str.replace(r'\s{2,}', ' ', regex=True)

out_path = 'nagpada/nagpada.eng.csv'
final.to_csv(out_path, index=False, encoding='utf-8-sig')

print(f"\n✅ Saved to: {out_path}")
print(f"   Total rows: {len(final)}")
print(final.head(3).to_string())