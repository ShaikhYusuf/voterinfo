"""
Chawl / Building Address Extractor from Maharashtra Voter List PDFs
====================================================================
Scans every page of a voter list PDF and extracts the address header
lines that contain a pincode (e.g. 400011, 400001).

In Maharashtra voter lists, each group of voters is preceded by a
section header like:
    म्यु.घ.नं.3 बी.आय.टी.चाळ नं.8 ... मुंबई शहर पिनकोड 400011

This script extracts those lines along with:
    - The PDF filename
    - The page number
    - The pincode found

OUTPUT: A plain text file (and optionally CSV) listing all addresses,
        useful for building a searchable index of chawls/buildings.

REQUIREMENTS:
    pip install pdf2image pytesseract

    # Tesseract + Marathi language pack (for proper Devanagari text):
    # Windows: https://github.com/UB-Mannheim/tesseract/wiki
    #          + mar.traineddata in tessdata folder
    # Linux:   sudo apt install tesseract-ocr tesseract-ocr-mar poppler-utils
    # macOS:   brew install tesseract tesseract-lang

USAGE:
    # Single PDF:
    python extract_chawls.py voter_list.pdf

    # Multiple PDFs at once:
    python extract_chawls.py file1.pdf file2.pdf file3.pdf

    # Entire folder of PDFs:
    python extract_chawls.py --folder D:\\arif\\SIR\\pdfs\\

    # With Marathi OCR (recommended for proper names):
    python extract_chawls.py --lang mar+eng voter_list.pdf

    # Custom output file:
    python extract_chawls.py voter_list.pdf --out chawl_index.txt

    # Also save as CSV (for Excel):
    python extract_chawls.py voter_list.pdf --csv

WINDOWS PATHS — update these two lines if needed:
"""

import re
import sys
import os
import csv
import argparse
from pathlib import Path

try:
    from pdf2image import convert_from_path
    import pytesseract
except ImportError:
    print("ERROR: Run:  pip install pdf2image pytesseract")
    sys.exit(1)

# ── WINDOWS USERS: SET YOUR PATHS HERE ─────────────────────────
TESSERACT_PATH = "C:/Program Files/Tesseract-OCR/tesseract.exe"
POPPLER_PATH   = "D:/poppler/Library/bin"

import os as _os
if _os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
# ────────────────────────────────────────────────────────────────

# Matches Maharashtra pincodes: 400001 – 445999
PINCODE_RE = re.compile(r'\b(4[0-3][0-9]{4})\b')

# Noise words to strip from OCR output before saving
NOISE_WORDS = re.compile(
    r'\b(ORT|Cast|Ga|GG|sts|firats|asts|dag|wer|Gs)\b', re.IGNORECASE
)


def clean_line(line):
    """Remove obvious OCR noise words while keeping Marathi and numbers."""
    line = NOISE_WORDS.sub('', line)
    line = re.sub(r'\s{2,}', ' ', line)  # collapse multiple spaces
    return line.strip()


def extract_chawl_lines(pdf_path, lang, poppler_path=None):
    """
    Process one PDF file and return list of dicts:
        { filename, page, pincode, address }
    """
    results = []
    filename = Path(pdf_path).name

    print(f"\n📄 Processing: {filename}")

    kwargs = {'dpi': 300}
    if poppler_path and _os.path.exists(poppler_path):
        kwargs['poppler_path'] = poppler_path

    try:
        images = convert_from_path(pdf_path, **kwargs)
    except Exception as e:
        print(f"   ❌ Could not open PDF: {e}")
        return results

    print(f"   {len(images)} pages found")

    for page_num, img in enumerate(images, 1):
        print(f"   Page {page_num:3d}...", end=" ", flush=True)

        try:
            text = pytesseract.image_to_string(img, lang=lang)
        except Exception:
            text = pytesseract.image_to_string(img, lang='eng')

        lines = [l.strip() for l in text.split('\n')]
        found = 0

        for i, line in enumerate(lines):
            match = PINCODE_RE.search(line)
            if match:
                pincode = match.group(1)

                # Find the last non-empty line above (min 5 chars to skip noise)
                prev_line = ''
                for j in range(i - 1, max(0, i - 6), -1):
                    if lines[j].strip() and len(lines[j].strip()) > 4:
                        prev_line = clean_line(lines[j].strip())
                        break

                # Combine: "line above  +  pincode line"
                pin_line  = clean_line(line)
                full_addr = f"{prev_line}  {pin_line}".strip() if prev_line else pin_line

                results.append({
                    'filename':  filename,
                    'page':      page_num,
                    'pincode':   pincode,
                    'line_above': prev_line,
                    'pin_line':  pin_line,
                    'address':   full_addr,
                })
                found += 1

        print(f"{found} address(es) found")

    return results


def write_text_output(results, output_path):
    """Write results as a readable indexed text file."""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("=" * 70 + "\n")
        f.write("CHAWL / BUILDING ADDRESS INDEX\n")
        f.write("Extracted from Maharashtra Voter List PDFs\n")
        f.write("=" * 70 + "\n\n")

        # Group by filename
        from itertools import groupby
        results_sorted = sorted(results, key=lambda x: (x['filename'], x['page']))

        current_file = None
        entry_num = 1

        for r in results_sorted:
            if r['filename'] != current_file:
                current_file = r['filename']
                f.write(f"\n{'─' * 70}\n")
                f.write(f"FILE: {current_file}\n")
                f.write(f"{'─' * 70}\n")

            f.write(
                f"{entry_num:4d}. "
                f"[Page {r['page']:3d}] "
                f"[PIN: {r['pincode']}]\n"
                f"      {r['address']}\n\n"
            )
            entry_num += 1

        f.write(f"\n{'=' * 70}\n")
        f.write(f"Total entries: {len(results)}\n")


def write_csv_output(results, output_path):
    """Write results as CSV for Excel."""
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(
            f,
            fieldnames=['filename', 'page', 'pincode', 'line_above', 'pin_line', 'address']
        )
        writer.writerow({
            'filename':   'PDF File',
            'page':       'Page No.',
            'pincode':    'Pincode',
            'line_above': 'Address Line 1',
            'pin_line':   'Address Line 2 (with Pincode)',
            'address':    'Full Address (Combined)',
        })
        writer.writerows(results)


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Extract chawl/building addresses with pincodes from voter list PDFs"
    )
    parser.add_argument("pdfs", nargs="*",
                        help="One or more PDF files to process")
    parser.add_argument("--folder", default=None,
                        help="Folder containing PDFs — processes all .pdf files in it")
    parser.add_argument("--lang", default="mar+eng",
                        help="Tesseract language (default: mar+eng)")
    parser.add_argument("--out", default="chawl_index.txt",
                        help="Output text file name (default: chawl_index.txt)")
    parser.add_argument("--csv", action="store_true",
                        help="Also save a CSV version for Excel")
    parser.add_argument("--poppler", default=None,
                        help="[Windows] Path to Poppler bin folder")
    parser.add_argument("--tesseract", default=None,
                        help="[Windows] Full path to tesseract.exe")
    args = parser.parse_args()

    # Apply custom paths if provided
    if args.tesseract and _os.path.exists(args.tesseract):
        pytesseract.pytesseract.tesseract_cmd = args.tesseract

    poppler = args.poppler or (POPPLER_PATH if _os.path.exists(POPPLER_PATH) else None)

    # Collect PDF files
    pdf_files = list(args.pdfs) if args.pdfs else []
    if args.folder:
        folder = Path(args.folder)
        pdf_files += sorted(folder.glob("*.pdf")))

    if not pdf_files:
        print("❌ No PDF files specified.")
        print("   Usage: python extract_chawls.py myfile.pdf")
        print("   Or:    python extract_chawls.py --folder D:\\my\\pdfs\\")
        sys.exit(1)

    print(f"\n🔍 Searching for addresses with pincodes in {len(pdf_files)} PDF(s)")
    print(f"🔤 OCR Language : {args.lang}")

    all_results = []
    for pdf_path in pdf_files:
        results = extract_chawl_lines(str(pdf_path), args.lang, poppler)
        all_results.extend(results)

    if not all_results:
        print("\n⚠️  No pincode address lines found.")
        print("   Try running with --lang mar+eng if not already.")
        sys.exit(0)

    # Write text output
    write_text_output(all_results, args.out)
    print(f"\n✅ Text index saved : {args.out}")

    # Write CSV if requested
    if args.csv:
        csv_path = args.out.replace('.txt', '.csv')
        write_csv_output(all_results, csv_path)
        print(f"✅ CSV saved        : {csv_path}")

    print(f"\n📊 Total addresses found : {len(all_results)}")
    print(f"   Across {len(pdf_files)} PDF file(s)\n")

    # Preview first 5 results
    print("Preview (first 5 entries):")
    print("-" * 70)
    for r in all_results[:5]:
        print(f"  [{r['filename']} | Page {r['page']}] {r['address']}")
    print()


if __name__ == "__main__":
    main()