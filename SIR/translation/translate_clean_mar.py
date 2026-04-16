"""
clean_addresses.py
------------------
Cleans and expands Marathi municipal addresses from a CSV file.

What it does:
  1. Fixes typos (मौलना → मौलाना, आझादे → आझाद, रोडपम्यु → रोड म्यु. etc.)
  2. Expands all known abbreviations to their full Marathi forms
  3. Fixes spacing — after section markers (अ) ब) क)…), around ते/आणि, etc.
  4. Removes stray characters ($, stray ॑, misplaced hyphens)
  5. Normalises multiple spaces

Reads from : chinchpokli.mar.csv
Writes to  : updated.chinchpokli.mar.csv  (adds original_content column)

Usage:
    python clean_addresses.py                          # uses default filenames
    python clean_addresses.py input.csv output.csv     # custom filenames
"""

import csv
import re
import sys
import os

DEFAULT_INPUT  = "chinchpokli.mar.csv"
DEFAULT_OUTPUT = "updated.chinchpokli.mar.csv"

# ============================================================================
# STEP 1 – TYPO / OCR CORRECTIONS
# Applied first so later rules see clean text.
# ============================================================================
TYPOS = [
    (r"(?<![\u0900-\u097F])मौलना(?![\u0900-\u097F])",          "मौलाना"),
    (r"मौलाना आझादे",        "मौलाना आझाद"),
    (r"\bडॉं\.",             "डॉ."),
    (r"\bडा\.",              "डॉ."),
    (r"रोडप(म्यु)",         r"रोड \1"),       # रोडपम्यु → रोड म्यु
    (r"ते\.म्यु",            "ते म्यु"),        # ते.म्यु → ते म्यु
    (r"जोश॑",               "जोशी"),           # stray chandrabindu
    (r"\$",                  ""),               # stray dollar sign
    (r"म्यु घ\.",            "म्यु.घ.नं."),        # errant space in म्यु घ.
    (r"म्य\. घ\.",           "म्यु.घ.नं."),        # म्य. घ. → म्यु.घ.
    (r"\म्यु\.\घ\.\नं\.",           "म्यु.घ.नं."),        # म्य.घ. → म्यु.घ.
]

# ============================================================================
# STEP 2 – ABBREVIATION EXPANSION
# Longer / more-specific patterns MUST come before shorter overlapping ones.
# ============================================================================
ABBREVIATIONS = [

    # ── Municipal ward identifier ────────────────────────────────────────
    (r"म\.न\.वि\.",              "महानगरपालिका"),
    (r"म\.न\.पा\.",              "महानगरपालिका"),
    (r"मनिवि(\d+)",              r"महानगरपालिका \1"),
    (r"मनिवि",                   "महानगरपालिका"),

    # ── Municipal house number — longest patterns first ──────────────────
    (r"म्यु\.घ\.नं\.क्रं\.",    "म्युनिसिपल घर क्रमांक"),
    (r"म्यु\.घ\.क्रं\.",        "म्युनिसिपल घर क्रमांक"),
    (r"म्यु\.घ\.नं\.",          "म्युनिसिपल घर क्रमांक"),
    (r"म्यु\.घ\.नु\.",          "म्युनिसिपल घर क्रमांक"),
    (r"म\.यु\.घ\.नं\.",         "म्युनिसिपल घर क्रमांक"),
    (r"म्यु\.घं\.नं\.",         "म्युनिसिपल घर क्रमांक"),
    (r"म्युनिसिपल घ\.नं\.",     "म्युनिसिपल घर क्रमांक"),
    (r"म्यु\.घ\.",               "म्युनिसिपल घर"),

    # ── Municipal number without घर ──────────────────────────────────────
    (r"म्यु\.नं\.",              "म्युनिसिपल क्रमांक"),

    # ── Municipal building ────────────────────────────────────────────────
    (r"म्यु\.बि\.नं\.",         "म्युनिसिपल बिल्डिंग क्रमांक"),
    (r"म्यु\.बि\.क्रं\.",       "म्युनिसिपल बिल्डिंग क्रमांक"),
    (r"म्यु\.बि\.न\.",          "म्युनिसिपल बिल्डिंग क्रमांक"),
    (r"म्यु\.बि\.",              "म्युनिसिपल बिल्डिंग"),
    (r"\bम्यु\.ब्लाँक\b",       "म्युनिसिपल ब्लॉक"),
    (r"\bम्यु\.चाळी\b",         "म्युनिसिपल चाळी"),
    (r"\bम्यु\.पत्रा चाळ\b",    "म्युनिसिपल पत्रा चाळ"),

    # ── Cooperative society ───────────────────────────────────────────────
    (r"कॉ\.ऑ\.सो\.",            "को-ऑपरेटिव्ह सोसायटी"),

    # ── Road / person name abbreviations ─────────────────────────────────
    (r"\bना\.म\.जोशी\b",        "नामदेव मुरलीधर जोशी"),
    (r"\bना\.म\.\b",             "नामदेव मुरलीधर "),
    (r"\bग\.ह\.पां\.मार्ग\b",   "गणेश हरी पारंडेकर मार्ग"),
    (r"\bग\.ह\.पा\.मार्ग\b",    "गणेश हरी पारंडेकर मार्ग"),
    (r"\bग\.ह\.पां\.",           "गणेश हरी पारंडेकर "),
    (r"\bग\.ह\.पा\.",            "गणेश हरी पारंडेकर "),
    (r"\bबा\.ज\.मार्ग\b",       "बापुराव जगताप मार्ग"),
    (r"\bबा\.ज\.\b",             "बापुराव जगताप "),
    (r"\bमे\.सेठी मार्ग\b",     "मेघराज सेठी मार्ग"),
    (r"\bमे\.सेठी\b",            "मेघराज सेठी"),
    (r"\bक\.खा\.मार्ग\b",       "केशवराव खाडये मार्ग"),
    (r"\bक\.खा\.\b",             "केशवराव खाडये "),
    (r"\bई\.एस\.पाटणबाल\b",     "ई. एस. पाटणबाल"),

    # ── Lane / street shortforms ──────────────────────────────────────────
    (r"\bम\.सि\.अ\.लेन\b",      "महंमद सिद्दीक अन्सारी लेन"),
    (r"\bमि\.स्ट्रीट\b",        "मिल्क स्ट्रीट"),
    (r"\bमो\.स्ट्रीट\b",        "मोहम्मद स्ट्रीट"),
    (r"\bमो\. स्ट्रीट\b",       "मोहम्मद स्ट्रीट"),
    (r"\bमौ\.आ\.रोड\b",         "मौलाना आझाद रोड"),
    (r"\bफा\.एस\.उमरभाई पथ\b",  "फारूख एस. उमरभाई पथ"),
    (r"\bफा\.एस\.\b",            "फारूख एस. "),
    (r"\bबॉ\.स्ट्रीट\b",        "बॉम्बे स्ट्रीट"),

    # ── Company / trust ───────────────────────────────────────────────────
    (r"कं\.प्रा\.लि\.",         "कंपनी प्रायव्हेट लिमिटेड"),
    (r"कं\. प्रा\. लि\.",       "कंपनी प्रायव्हेट लिमिटेड"),

    # ── Slum / chawl shortforms ───────────────────────────────────────────
    (r"\bझो\.सं\.\b",           "झोपडपट्टी संघ"),
    (r"\bझोप\.\b",              "झोपडपट्टी"),
    (r"\bबि\.नं\.",              "बिल्डिंग क्रमांक"),
    (r"\bबि\.मा\.\b",           "बिल्डिंग माळा"),
    (r"\bबि\.ते\.\b",           "बिल्डिंग ते"),
    (r"\bपा\.मा\.झो\.\b",       "पत्रा माळा झोपडपट्टी"),
    (r"\bप\.चाळ\b",             "पत्रा चाळ"),
    (r"\bल\.चाळ\b",             "लाल चाळ"),
    (r"\bन्यू ल\.चाळ\b",        "न्यू लाल चाळ"),

    # ── Specific chawl / person name shortforms ───────────────────────────
    (r"\bपी\.म\.चाळ\b",         "पीर महंमद चाळ"),
    (r"\bयु\.हा\.कासम\b",       "युसुफ हाजी कासम"),

    # ── Survey / house number variants ────────────────────────────────────
    (r"\bसौ\.एच\.नं\.",         "सर्व्हे हाऊस क्रमांक"),
    (r"\bसी\.एच\.नं\.",         "सिटी हाऊस क्रमांक"),

    # ── Generic number abbreviations — MUST be last (shortest) ───────────
    (r"\bक्रं\b",               "क्रमांक"),
    (r"\bक्र\.\b",              "क्रमांक"),
    (r"(?<!क्रमांक )नं\.",      "क्रमांक "),
]

# ============================================================================
# STEP 3 – SPACING FIXES
# ============================================================================

def fix_spacing(text: str) -> str:
    # Ensure space AFTER section marker: अ) ब) क) ड) इ) …
    text = re.sub(r'([\u0900-\u097F])\)(?!\s)', r'\1) ', text)

    # Insert " | " before each sub-section marker not at the start
    text = re.sub(r'(?<=[^\s|])\s+([\u0900-\u097F]\))', r'  |  \1', text)

    # Space around ते when squished
    text = re.sub(r'(?<=[^\s])ते(?=[^\s])', ' ते ', text)

    # Space after comma if missing
    text = re.sub(r',(?!\s)', ', ', text)

    # Remove space BEFORE  . , )
    text = re.sub(r'\s+([.,)])', r'\1', text)

    # Ensure space AFTER  .  unless followed by digit or whitespace
    text = re.sub(r'\.(?=[^\s\d])', '. ', text)

    # Space between digit and Devanagari letter (e.g. 91डी → 91 डी)
    text = re.sub(r'(\d)([\u0900-\u097F])', r'\1 \2', text)
    text = re.sub(r'([\u0900-\u097F])(\d)', r'\1 \2', text)

    # Collapse runs of spaces
    text = re.sub(r'  +', ' ', text)

    # Normalise hyphen in numeric ranges  22 - 24 → 22-24
    text = re.sub(r'(?<=\d)\s*-\s*(?=\d)', '-', text)

    # Leading " -ब)" style separators → " | ब)"
    text = re.sub(r'\s+-\s*(?=[\u0900-\u097F]\))', '  |  ', text)

    return text.strip()

# ============================================================================
# PIPELINE
# ============================================================================

def apply_typos(text):
    for pat, rep in TYPOS:
        text = re.sub(pat, rep, text)
    return text

def expand_abbreviations(text):
    for pat, rep in ABBREVIATIONS:
        text = re.sub(pat, rep, text)
    return text

def clean_address(raw):
    text = raw.strip().strip('"')
    text = apply_typos(text)
    text = expand_abbreviations(text)
    text = fix_spacing(text)
    return text

# ============================================================================
# CSV PROCESSING
# ============================================================================

def process_csv(input_path, output_path):
    with open(input_path, newline='', encoding='utf-8') as fin:
        reader = csv.DictReader(fin)
        fieldnames = list(reader.fieldnames or [])
        if 'content' not in fieldnames:
            raise ValueError(f"No 'content' column found. Columns: {fieldnames}")
        rows = list(reader)

    out_fields = fieldnames + ['original_content']
    cleaned_rows = []
    for row in rows:
        original = row['content']
        new_row  = dict(row)
        new_row['content']          = clean_address(original)
        # new_row['original_content'] = original
        cleaned_rows.append(new_row)

    with open(output_path, 'w', newline='', encoding='utf-8') as fout:
        writer = csv.DictWriter(fout, fieldnames=out_fields)
        writer.writeheader()
        writer.writerows(cleaned_rows)

    print(f"✓  {len(cleaned_rows)} rows cleaned")
    print(f"   Input : {input_path}")
    print(f"   Output: {output_path}")

# ============================================================================
# MAIN
# ============================================================================
if __name__ == "__main__":
    if len(sys.argv) == 3:
        process_csv(sys.argv[1], sys.argv[2])
    elif len(sys.argv) == 2:
        process_csv(sys.argv[1], DEFAULT_OUTPUT)
    elif len(sys.argv) == 1:
        if os.path.exists(DEFAULT_INPUT):
            process_csv(DEFAULT_INPUT, DEFAULT_OUTPUT)
        else:
            print(f"\nPlace your CSV at '{DEFAULT_INPUT}' and run again, or:")
            print("  python clean_addresses.py input.csv output.csv")
    else:
        print("Usage: python clean_addresses.py [input.csv [output.csv]]")
        sys.exit(1)