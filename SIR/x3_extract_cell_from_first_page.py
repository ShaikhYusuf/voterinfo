"""
यादी भागाच्या हद्दीचा तपशील Cell Extractor
=============================================
Extracts the boundary description cell from page 1 of Maharashtra
voter list PDFs. Outputs CSV with: Filename, Page No., Yadi Bhag No., Content.

REQUIREMENTS:
    pip install pdf2image pytesseract pandas Pillow

    # Tesseract + Marathi pack:
    # Windows:  https://github.com/UB-Mannheim/tesseract/wiki
    #           + mar.traineddata in C:\\Program Files\\Tesseract-OCR\\tessdata\\
    # Linux:    sudo apt install tesseract-ocr tesseract-ocr-mar poppler-utils
    # macOS:    brew install tesseract tesseract-lang

USAGE:
    python extract_yadi_cell.py voter_list.pdf
    python extract_yadi_cell.py --folder D:\\arif\\SIR\\pdfs\\ --lang mar+eng
    python extract_yadi_cell.py voter_list.pdf --out output.csv
"""

import re, sys, os, csv, argparse
from pathlib import Path

try:
    from pdf2image import convert_from_path
    import pytesseract
    import pandas as pd
    from PIL import ImageEnhance
except ImportError:
    print("ERROR: Run:  pip install pdf2image pytesseract pandas Pillow")
    sys.exit(1)

# ── WINDOWS USERS: UPDATE THESE PATHS ──────────────────────────
TESSERACT_PATH = "C:/Program Files/Tesseract-OCR/tesseract.exe"
POPPLER_PATH   = "D:/poppler/Library/bin"
if os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
# ───────────────────────────────────────────────────────────────


def extract_yadi_bhag_no(images, lang):
    """
    Extract Yadi Bhag number (e.g. 0009) reliably.
    Strategy: check page 2 header text which contains it more clearly,
    or fall back to page 1.
    """
    # Try page 2 first (header line contains "0009" style number)
    pages_to_check = images[:2] if len(images) >= 2 else images

    for img in reversed(pages_to_check):  # page 2 first, then page 1
        try:
            text = pytesseract.image_to_string(img, lang=lang)
        except Exception:
            text = pytesseract.image_to_string(img, lang='eng')

        for line in text.split('\n')[:8]:  # only check top lines
            match = re.search(r'0{1,2}(\d{3,4})\b', line)
            if match:
                raw = match.group(0)
                # Normalize: strip leading zeros, repad to 4 digits
                num = raw.lstrip('0') or '0'
                return num.zfill(4)

    return ''


def find_cell_boundaries(df, img_height):
    """
    Find Y pixel boundaries of the यादी भागाच्या हद्दीचा तपशील cell.

    Top:    label row "यादी भागाच्या..." at left margin
            (OCR eng reads as 'areal', 'Sea', 'Sera')
    Bottom: section 3 polling station 3-digit number in lower half
            (e.g. '009') — or fixed fallback at 56% page height
    """
    # Top boundary
    label = df[
        (df['left'] < 700) &
        (df['text'].str.lower().str.contains(r'areal|sera|sea|yadi|tart', regex=True))
    ]
    y_top = int(label['top'].min()) + 45 if not label.empty else int(img_height * 0.315)

    # Bottom boundary: section 3 polling number (e.g. "009")
    sec3 = df[df['text'].str.match(r'^0\d{2}$') & (df['top'] > img_height * 0.50)]
    y_bottom = int(sec3['top'].min()) - 50 if not sec3.empty else int(img_height * 0.56)

    # Safety check
    if y_bottom <= y_top:
        y_bottom = y_top + int(img_height * 0.20)

    return y_top, y_bottom


def extract_cell_content(image, lang):
    """Crop and OCR the content of the yadi cell. Returns cleaned text."""
    w, h = image.size

    # Get word positions for boundary detection
    raw = pytesseract.image_to_data(image, lang=lang, output_type=pytesseract.Output.DICT)
    df  = pd.DataFrame(raw)
    df  = df[(df['conf'] > 15) & (df['text'].str.strip() != '')]

    y_top, y_bottom = find_cell_boundaries(df, h)

    # Crop: skip narrow left label area, go to right margin
    crop = image.crop((420, y_top, w - 80, y_bottom))
    crop = ImageEnhance.Contrast(crop).enhance(1.8)

    try:
        text = pytesseract.image_to_string(crop, lang=lang)
    except Exception:
        text = pytesseract.image_to_string(crop, lang='eng')

    # Clean: join non-trivial lines with " | " separator
    lines = [l.strip() for l in text.split('\n') if len(l.strip()) > 3]
    content = ' | '.join(lines)
    content = re.sub(r'\s{2,}', ' ', content).strip()

    return content, y_top, y_bottom


def process_pdf(pdf_path, lang, poppler_path=None):
    """Process one PDF, return list of result dicts."""
    filename = Path(pdf_path).name
    print(f"\n📄 {filename}")

    kwargs = {'dpi': 300}
    if poppler_path and os.path.exists(poppler_path):
        kwargs['poppler_path'] = poppler_path

    try:
        # Load page 1 (and page 2 if it exists, for bhag number extraction)
        images = convert_from_path(pdf_path, first_page=1, last_page=2, **kwargs)
    except Exception as e:
        print(f"   ❌ Could not open: {e}")
        return []

    # Extract Yadi Bhag number
    yadi_bhag_no = extract_yadi_bhag_no(images, lang)

    # Extract cell content from page 1
    img_p1 = images[0]
    w, h = img_p1.size
    print(f"   Page size  : {w}×{h}px")
    print(f"   Yadi Bhag  : {yadi_bhag_no or '(not found)'}")

    content, y_top, y_bottom = extract_cell_content(img_p1, lang)
    print(f"   Cell region: y={y_top}–{y_bottom}")
    print(f"   Content    : {content[:100]}{'...' if len(content)>100 else ''}")

    return [{
        'filename':     filename,
        'page_no':      1,
        'yadi_bhag_no': yadi_bhag_no,
        'content':      content,
    }]


def save_csv(results, output_path):
    fieldnames = ['filename', 'page_no', 'yadi_bhag_no', 'content']
    headers    = [
        'Filename',
        'Page No.',
        'यादी भाग क्रमांक (Yadi Bhag No.)',
        'यादी भागाच्या हद्दीचा तपशील (Content)',
    ]
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writerow(dict(zip(fieldnames, headers)))
        writer.writerows(results)


def main():
    parser = argparse.ArgumentParser(
        description="Extract yadi bhagachya haddichya tapsil from voter list PDFs"
    )
    parser.add_argument("pdfs",        nargs="*",           help="PDF file(s)")
    parser.add_argument("--folder",    default=None,        help="Folder of PDFs")
    parser.add_argument("--lang",      default="mar+eng",   help="OCR language (default: mar+eng)")
    parser.add_argument("--out",       default="yadi_cell_index.csv", help="Output CSV")
    parser.add_argument("--poppler",   default=None,        help="[Win] Poppler bin path")
    parser.add_argument("--tesseract", default=None,        help="[Win] tesseract.exe path")
    args = parser.parse_args()

    if args.tesseract and os.path.exists(args.tesseract):
        pytesseract.pytesseract.tesseract_cmd = args.tesseract

    poppler = args.poppler or (POPPLER_PATH if os.path.exists(POPPLER_PATH) else None)

    pdf_files = list(args.pdfs) if args.pdfs else []
    if args.folder:
        folder = Path(args.folder)
        pdf_files_set = set(folder.glob("*.pdf")) | set(folder.glob("*.PDF"))
        pdf_files += sorted(pdf_files_set)

    if not pdf_files:
        print("No PDFs found.\nUsage: python extract_yadi_cell.py myfile.pdf")
        sys.exit(1)

    print(f"\n🔍 Processing {len(pdf_files)} PDF(s) | lang={args.lang}")

    all_results = []
    for pdf in pdf_files:
        all_results.extend(process_pdf(str(pdf), args.lang, poppler))

    if not all_results:
        print("\n⚠️  No results extracted.")
        sys.exit(0)

    save_csv(all_results, args.out)

    print(f"\n{'='*60}")
    print(f"✅ {len(all_results)} record(s) saved to: {args.out}")
    print(f"{'='*60}")
    print(f"\n{'Filename':<35} {'Bhag':>6}")
    print(f"{'─'*45}")
    for r in all_results:
        print(f"{r['filename']:<35} {r['yadi_bhag_no']:>6}")
    print()

if __name__ == "__main__":
    main()