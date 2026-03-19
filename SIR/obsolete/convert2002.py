"""
Maharashtra Voter List PDF → CSV Extractor
==========================================
Tested on: 2002 format voter list (025 - Chinchpokli, Yadi Bhag 0009)
Works for: Any Maharashtra voter list with the same tabular format

WHAT IT DOES:
- Converts scanned PDF pages to images
- Runs OCR (Tesseract) on each page
- Reconstructs table columns using word X-positions
- Outputs a clean CSV with all voter records

COLUMNS EXTRACTED:
    (1) अ.क्र.              - Serial Number
    (2) घर क्रमांक          - House Number
    (3) मतदाराचे पूर्ण नाव  - Voter Full Name  *
    (4) नाते                - Relation         *
    (5) नातेवाईकाचे पूर्ण नाव - Relative Name  *
    (6) लिंग                - Gender
    (7) वय                  - Age
    (8) ओळख पत्र क्रमांक    - Voter ID

    * Names/relations appear garbled without Marathi Tesseract pack.
      Install it for proper Devanagari text (see below).

REQUIREMENTS:
    pip install pdf2image pytesseract pandas

    # Tesseract OCR (required):
    # Ubuntu/Debian:  sudo apt install tesseract-ocr tesseract-ocr-mar poppler-utils
    # macOS:          brew install tesseract tesseract-lang
    # Windows:        https://github.com/UB-Mannheim/tesseract/wiki
    #                 + download mar.traineddata to Tesseract tessdata folder

USAGE:
    # English OCR only (Voter ID, Age, Sr.No. reliable; names garbled):
    python extract_voters_table.py voter_list.pdf

    # With Marathi OCR (proper Devanagari names):
    python extract_voters_table.py voter_list.pdf --lang mar+eng

    # Custom output filename:
    python extract_voters_table.py voter_list.pdf --out my_voters.csv

    # Higher DPI for better accuracy (slower):
    python extract_voters_table.py voter_list.pdf --dpi 300

    # Process specific pages only (e.g. pages 2 to 10):
    python extract_voters_table.py voter_list.pdf --pages 2-10

HOW COLUMN DETECTION WORKS:
    This PDF is a scanned image — there is no embedded text.
    We use Tesseract's word-level bounding boxes (image_to_data) to get
    the X position of every word, then assign each word to a column
    based on X ranges calibrated from this PDF format.
    Words on the same Y row (within 20px) are grouped into one record.
"""

import re
import sys
import csv
import argparse
import pandas as pd

try:
    from pdf2image import convert_from_path
    import pytesseract
except ImportError:
    print("ERROR: Run:  pip install pdf2image pytesseract pandas")
    sys.exit(1)

# ── WINDOWS USERS: SET YOUR PATHS HERE ────────────────────────
# Update these two lines to match where you installed the tools.
# After setting them, you can run the script with NO extra flags.
import os as _os

TESSERACT_PATH = "C:/Program Files/Tesseract-OCR/tesseract.exe"
POPPLER_PATH   = "D:/poppler/Library/bin"

if _os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
# ───────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────
# COLUMN X-POSITION BOUNDARIES  (calibrated at 250 DPI)
# Adjust these if your PDF has a different layout/scan resolution
# ─────────────────────────────────────────────────────────────
#
#  Col name      X_start   X_end   (pixels at 250 DPI)
#  ─────────────────────────────────────────────────────
#  sr_no          290       360    अ.क्र.
#  house_no       360       440    घर क्रमांक
#  name           440      1010    मतदाराचे पूर्ण नाव
#  relation      1010      1100    नाते (प=पती, व=वडील etc.)
#  rel_name      1100      1500    नातेवाईकाचे पूर्ण नाव
#  gender        1500      1600    लिंग (स्त्री/पुरुष)
#  age           1600      1640    वय
#  voter_id      1640      2000    ओळख पत्र क्रमांक

BASE_DPI = 250

COL_BOUNDS_250DPI = {
    'sr_no':    (270,  355),   # अ.क्र.
    'house_no': (355,  445),   # घर क्रमांक
    'name':     (445,  1020),  # मतदाराचे पूर्ण नाव
    'relation': (1020, 1115),  # नाते
    'rel_name': (1115, 1490),  # नातेवाईकाचे पूर्ण नाव
    'gender':   (1490, 1595),  # लिंग
    'age':      (1595, 1645),  # वय
    'voter_id': (1645, 2100),  # ओळख पत्र क्रमांक
}


def scale_bounds(bounds, dpi):
    """Scale column X boundaries for the chosen DPI."""
    scale = dpi / BASE_DPI
    return {k: (int(v[0] * scale), int(v[1] * scale)) for k, v in bounds.items()}


# ─────────────────────────────────────────────────────────────
# TABLE START DETECTION
# ─────────────────────────────────────────────────────────────

def find_table_start_y(df):
    """
    Find the Y pixel where the actual voter data begins.
    We look for the first row where column 1 has a single digit (serial number).
    This skips the page header, column headers, and address blocks.
    """
    df_sorted = df.sort_values(['top', 'left'])
    for _, row in df_sorted.iterrows():
        if re.match(r'^\d{1,3}$', str(row['text']).strip()) and row['left'] < 400:
            return row['top'] - 10  # give 10px buffer above first data row
    return 400  # fallback: assume table starts at y=400


# ─────────────────────────────────────────────────────────────
# SINGLE PAGE EXTRACTION
# ─────────────────────────────────────────────────────────────

def extract_table_from_page(image, page_num, lang, dpi):
    """
    Extract voter table rows from a single page image.
    Returns a list of dicts, one per voter row.
    """
    col_bounds = scale_bounds(COL_BOUNDS_250DPI, dpi)

    # Get word-level OCR data with bounding boxes
    raw = pytesseract.image_to_data(image, lang=lang, output_type=pytesseract.Output.DICT)
    df = pd.DataFrame(raw)

    # Filter: remove low-confidence and empty words
    df = df[df['conf'] > 15]
    df = df[df['text'].str.strip() != '']

    # Find where table data starts (skip page headers)
    table_start_y = find_table_start_y(df)
    df = df[df['top'] >= table_start_y]

    if df.empty:
        return []

    # ── Group words into rows by Y proximity ──
    df = df.sort_values(['top', 'left']).reset_index(drop=True)
    word_rows = []
    current_group = []
    current_y = None

    for _, word in df.iterrows():
        if current_y is None or abs(word['top'] - current_y) > 20:
            if current_group:
                word_rows.append(current_group)
            current_group = [word]
            current_y = word['top']
        else:
            current_group.append(word)
    if current_group:
        word_rows.append(current_group)

    # ── Assign each word to a column by X position ──
    records = []
    for word_row in word_rows:
        record = {col: [] for col in col_bounds}

        for word in word_row:
            x = word['left']
            for col, (x_min, x_max) in col_bounds.items():
                if x_min <= x < x_max:
                    record[col].append(str(word['text']).strip())
                    break

        row_data = {col: ' '.join(words).strip() for col, words in record.items()}
        row_data['page'] = page_num

        # ── Fix merged Sr No + House No ──────────────────────────
        # When two numbers appear in sr_no (e.g. "4457"), it means
        # OCR merged serial 44 and house 57 into one cell.
        # We detect this by checking if sr_no > 999 and splitting it.
        sr_raw = row_data.get('sr_no', '').strip()
        hn_raw = row_data.get('house_no', '').strip()

        if re.match(r'^\d{3,6}$', sr_raw) and not hn_raw:
            # Try splitting: last 1-3 digits = house_no, rest = sr_no
            # e.g. "4457" → sr=44, house=57 | "3611" → sr=36, house=11
            for split in [2, 3, 1]:
                candidate_sr    = sr_raw[:-split]
                candidate_house = sr_raw[-split:]
                if candidate_sr and int(candidate_sr) <= 999:
                    row_data['sr_no']    = candidate_sr
                    row_data['house_no'] = candidate_house
                    sr_raw = candidate_sr
                    break

        # Only keep rows that have a valid serial number (1–3 digits)
        # This skips address lines, subtitles, footers
        if not (sr_raw and re.match(r'^\d{1,3}$', sr_raw)):
            continue

        # Skip footer lines (e.g. "रकाना 4 प-पती व-बडील...")
        name = row_data.get('name', '')
        if any(x in name for x in ['रकाना', 'प-पती', 'पु-पुरुष']):
            continue

        # Skip completely empty rows (OCR found sr_no but nothing else)
        non_empty = [v for k, v in row_data.items()
                     if k not in ('sr_no', 'page') and str(v).strip()]
        if not non_empty:
            # Still include it but mark as missing
            row_data['needs_review'] = 'YES - row appears blank in scan'

        # Clean age: remove non-digits ("53." → "53")
        row_data['age'] = re.sub(r'[^\d]', '', row_data['age'])

        # Clean house_no: remove non-digits and OCR noise
        row_data['house_no'] = re.sub(r'[^\d]', '', row_data['house_no'])

        # Normalize gender field
        g = row_data.get('gender', '')
        if re.search(r'स्त्री|महिला|स्री|स्रि', g):
            row_data['gender'] = 'स्त्री'
        elif re.search(r'पुरुष|पुरूष|पुरु', g):
            row_data['gender'] = 'पुरुष'
        else:
            row_data['gender'] = ''

        # Normalize relation: strip surname that bleeds in, keep last token
        # e.g. "सावरडेकर प" → "प", "रहाटे q" → "प"
        rel = row_data.get('relation', '').strip()
        rel_tokens = rel.split()
        rel = rel_tokens[-1] if rel_tokens else rel  # take last token only
        rel_map = {
            'प': 'प', 'य': 'प', 'q': 'प', 'T': 'प',   # पती
            'व': 'व', 'a': 'व', 'b': 'व', 'ब': 'व',   # वडील
            'स': 'स', 'सय': 'स', 'F': 'स',             # स्वतः
            'आ': 'आ',                                     # आई
        }
        row_data['relation'] = rel_map.get(rel, rel)

        # Clean voter ID: fix common OCR substitutions
        vid = row_data.get('voter_id', '')
        vid = re.sub(r'^[Mm][7Tt]/', 'MT/', vid)        # M7/ or Mt/ → MT/
        vid = re.sub(r'^एा\d', 'MT/0', vid)             # एा705 → MT/05
        vid = re.sub(r'^[Mm][Tt](\d)', r'MT/\1', vid)  # MT05 → MT/05
        # If it doesn't look like a valid ID, blank it out
        if vid and not re.match(r'^MT/\d{2}/\d{3}/\d{7}', vid):
            vid = vid  # keep as-is for manual review
        row_data['voter_id'] = vid

        records.append(row_data)

    return records


# ─────────────────────────────────────────────────────────────
# CSV WRITER
# ─────────────────────────────────────────────────────────────

CSV_HEADERS = [
    'page',
    'sr_no',
    'house_no',
    'name',
    'relation',
    'rel_name',
    'gender',
    'age',
    'voter_id',
]

CSV_DISPLAY_HEADERS = [
    'PDF Page',
    'अ.क्र. (Sr No)',
    'घर क्रमांक (House No)',
    'मतदाराचे नाव (Voter Name)',
    'नाते (Relation)',
    'नातेवाईकाचे नाव (Relative Name)',
    'लिंग (Gender)',
    'वय (Age)',
    'ओळख पत्र क्रमांक (Voter ID)',
]


def save_to_csv(records, output_path):
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        # utf-8-sig adds BOM so Excel opens Devanagari text correctly
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction='ignore')
        writer.writerow(dict(zip(CSV_HEADERS, CSV_DISPLAY_HEADERS)))
        writer.writerows(records)


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Extract Maharashtra voter list table from scanned PDF to CSV"
    )
    parser.add_argument("pdf",
                        help="Path to voter list PDF file")
    parser.add_argument("--lang", default="eng",
                        help="Tesseract language. Use 'mar+eng' if Marathi pack is installed (default: eng)")
    parser.add_argument("--out", default="voters_extracted.csv",
                        help="Output CSV filename (default: voters_extracted.csv)")
    parser.add_argument("--dpi", default=250, type=int,
                        help="Image DPI for OCR — higher is more accurate but slower (default: 250)")
    parser.add_argument("--pages", default=None,
                        help="Page range e.g. '2-10' (default: all pages)")
    parser.add_argument("--poppler", default=None,
                        help="[Windows only] Path to Poppler bin folder e.g. D:\\poppler\\Library\\bin")
    parser.add_argument("--tesseract", default=None,
                        help="[Windows only] Full path to tesseract.exe e.g. C:\\Program Files\\Tesseract-OCR\\tesseract.exe")
    args = parser.parse_args()

    first_page = last_page = None
    if args.pages:
        parts = args.pages.split('-')
        first_page = int(parts[0])
        last_page  = int(parts[1]) if len(parts) > 1 else int(parts[0])

    print(f"\n📄 PDF     : {args.pdf}")
    print(f"🔤 Language: {args.lang}")
    print(f"🖼  DPI     : {args.dpi}")
    if first_page:
        print(f"📑 Pages   : {first_page}–{last_page}")
    print("\nConverting PDF pages to images...")

    kwargs = {'dpi': args.dpi}
    if first_page:   kwargs['first_page']   = first_page
    if last_page:    kwargs['last_page']    = last_page
    # Use hardcoded POPPLER_PATH as fallback if --poppler not passed
    poppler = args.poppler or (POPPLER_PATH if _os.path.exists(POPPLER_PATH) else None)
    if poppler: kwargs['poppler_path'] = poppler

    # Use hardcoded TESSERACT_PATH as fallback if --tesseract not passed
    tesseract = args.tesseract or TESSERACT_PATH
    if _os.path.exists(tesseract):
        pytesseract.pytesseract.tesseract_cmd = tesseract

    images = convert_from_path(args.pdf, **kwargs)
    print(f"   {len(images)} page(s) loaded.\n")

    all_records  = []
    start_offset = (first_page - 1) if first_page else 0

    for idx, img in enumerate(images):
        page_num = start_offset + idx + 1
        print(f"  Page {page_num:3d} ... ", end="", flush=True)
        records = extract_table_from_page(img, page_num, args.lang, args.dpi)
        print(f"{len(records)} voter rows extracted")
        all_records.extend(records)

    print(f"\n✅ Total voter rows : {len(all_records)}")
    print(f"💾 Saving to       : {args.out}")

    save_to_csv(all_records, args.out)

    # Quick summary
    has_voter_id = sum(1 for r in all_records if r.get('voter_id', '').startswith('MT/'))
    print(f"   Rows with Voter ID : {has_voter_id}")
    print(f"\n✅ Done! Open {args.out} in Excel.\n")
    if 'mar' not in args.lang:
        print("💡 TIP: Names are garbled because Marathi OCR pack is not installed.")
        print("        Install it and re-run with --lang mar+eng for proper Devanagari names.\n")


if __name__ == "__main__":
    main()
