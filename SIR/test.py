import pdfplumber
import csv
import argparse
from pathlib import Path

# ─────────────────────────────────────────────────────────────
# STEP 2: SakalMarathi → Unicode mapping (sample ISFOC mapping)
# NOTE: Replace/extend with full mapping from the converter repo
# ─────────────────────────────────────────────────────────────

SAKAL_MAP = {
    "¬": "अ",
    "¥": "आ",
    "ƒ": "इ",
    "⁄": "ई",
    "‹": "उ",
    "›": "ऊ",
    "−": "ए",
    "‰": "ऐ",
    "„": "ओ",
    "“": "औ",
    "’": "क",
    "‚": "ख",
    "™": "ग",
    "ﬁ": "घ",
    "ﬂ": "च",
    "‡": "छ",
    "·": "ज",
    "‚": "झ",
    "—": "ट",
    "˜": "ठ",
    "™": "ड",
    "š": "ढ",
    "›": "ण",
    # Extend mapping as needed...
}

def convert_sakal_to_unicode(text):
    for k, v in SAKAL_MAP.items():
        text = text.replace(k, v)
    return text

# ─────────────────────────────────────────────────────────────
# STEP 1: Extract text using pdfplumber
# ─────────────────────────────────────────────────────────────

def extract_text_from_pdf(pdf_path):
    results = []
    filename = Path(pdf_path).name

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            if i < 1:
                continue  # Skip first page
            
            raw_text = page.extract_words() or ""

            print(f"Extracted from {filename} (Page {i+1}): {raw_text[:10]}...")
            # Step 2: Convert font encoding
            # converted_text = convert_sakal_to_unicode(raw_text)
            converted_text = raw_text

            # # Clean multiline into single cell
            # clean_text = " ".join(
            #     [line.strip() for line in converted_text.split("\n") if line.strip()]
            # )

            # results.append(converted_text)
            break

    return results

# ─────────────────────────────────────────────────────────────
# CSV OUTPUT
# ─────────────────────────────────────────────────────────────

def save_csv(results, output_path):
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        for row in results:
            writer.writerow([row])

# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Extract SakalMarathi text and convert to Unicode")
    parser.add_argument("pdfs", nargs="*", help="PDF files")
    parser.add_argument("--folder", help="Folder containing PDFs")
    parser.add_argument("--out", default="output.csv", help="Output CSV file")

    args = parser.parse_args()

    pdf_files = list(args.pdfs)

    if args.folder:
        p = Path(args.folder)
        pdf_files += list(p.glob("*.pdf"))

    if not pdf_files:
        print("No PDFs found.")
        return

    all_results = []

    for pdf in pdf_files:
        res = extract_text_from_pdf(pdf)
        all_results.extend(res)

    save_csv(all_results, args.out)
    print(f"Saved → {args.out}")

if __name__ == "__main__":
    main()
    
[{'text': 'नतदहन', 'x0': 207.3, 'x1': 242.6808, 'top': 23.832949999999983, 'doctop': 865.83295, 'bottom': 35.98294999999996, 'upright': True, 'height': 12.149999999999977, 'width': 35.380799999999994, 'direction': 'ltr'}, 
 {'text': 'कक', 'x0': 245.80335000000002, 'x1': 256.20375, 'top': 23.832949999999983, 'doctop': 865.83295, 'bottom': 35.98294999999996, 'upright': True, 'height': 12.149999999999977, 'width': 10.40039999999999, 'direction': 'ltr'}, 
 {'text': 'दलनहहय', 'x0': 256.15, 'x1': 294.7384, 'top': 23.832949999999983, 'doctop': 865.83295, 'bottom': 35.98294999999996, 'upright': True, 'height': 12.149999999999977, 'width': 38.588400000000036, 'direction': 'ltr'}, 
 {'text': 'नतदहर', 'x0': 297.86095, 'x1': 331.7716, 'top': 23.832949999999983, 'doctop': 865.83295, 'bottom': 35.98294999999996, 'upright': True, 'height': 12.149999999999977, 'width': 33.910649999999976, 'direction': 'ltr'}, 
 {'text': 'यहदद', 'x0': 334.89414999999997, 'x1': 358.0885, 'top': 23.832949999999983, 'doctop': 865.83295, 'bottom': 35.98294999999996, 'upright': True, 'height': 12.149999999999977, 'width': 23.194350000000043, 'direction': 'ltr'}, 
 {'text': 'लदनहनक', 'x0': 484.5, 'x1': 509.6076, 'top': 22.043949999999995, 'doctop': 864.04395, 'bottom': 31.193949999999973, 'upright': True, 'height': 9.149999999999977, 'width': 25.10759999999999, 'direction': 'ltr'}, {'text': '1/3/2026', 'x0': 514.2, 'x1': 554.0208, 'top': 23.793949999999995, 'doctop': 865.79395, 'bottom': 32.94394999999997, 'upright': True, 'height': 9.149999999999977, 'width': 39.82079999999996, 'direction': 'ltr'}, {'text': '12:00:00AM', 'x0': 558.7239000000001, 'x1': 608.1156000000001, 'top': 23.793949999999995, 'doctop': 865.79395, 'bottom': 32.94394999999997, 'upright': True, 'height': 9.149999999999977, 'width': 49.391700000000014, 'direction': 'ltr'}, {'text': 'बबहननननबई', 'x0': 18.0, 'x1': 46.8545, 'top': 30.76049999999998, 'doctop': 872.7605, 'bottom': 39.26049999999998, 'upright': True, 'height': 8.5, 'width': 28.8545, 'direction': 'ltr'}, {'text': 'नहहनगरपहललकह', 'x0': 49.039, 'x1': 104.646, 'top': 30.76049999999998, 'doctop': 872.7605, 'bottom': 39.26049999999998, 'upright': True, 'height': 8.5, 'width': 55.607, 'direction': 'ltr'}]

"नतदहन कक दलनहहय नतदहर यहदद लदनहनक 1/3/2026 12:00:00AM

52.799999 185.119995 m
292.160004 185.119995 l
292.160004 194.880005 l
52.799999 194.880005 l