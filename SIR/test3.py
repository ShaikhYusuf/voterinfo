import sys
from pathlib import Path
import fitz  # PyMuPDF
import hashlib

def extract_sakalmarathi_with_pymupdf(pdf_path: str, output_dir: str = "extracted_fonts"):
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    if not pdf_path.exists():
        print(f"Error: PDF not found: {pdf_path}")
        return

    print(f"Extracting fonts using PyMuPDF from: {pdf_path.name}")
    print("-" * 80)

    doc = fitz.open(pdf_path)
    seen_hashes = set()
    saved_count = 0

    for page_num in range(len(doc)):
        page = doc[page_num]
        
        # Get list of fonts used on this page
        font_list = page.get_fonts(full=True)   # full=True gives more details

        for f in font_list:
            try:
                xref = f[0]          # xref number of the font
                ext = f[1]           # extension like 'ttf'
                font_type = f[2]
                font_name = f[3]     # e.g. AAAAAA+SakalMarathi

                if not xref:
                    continue

                # Extract raw font buffer using xref
                font_buffer = doc.extract_font(xref)
                if not font_buffer:
                    continue

                font_data = font_buffer[0]   # bytes of the font

                font_hash = hashlib.md5(font_data).hexdigest()
                if font_hash in seen_hashes:
                    continue
                seen_hashes.add(font_hash)

                # Detect SakalMarathi
                name_lower = font_name.lower()
                if "sakalmarathi" in name_lower or "sakal" in name_lower:
                    base_name = "SakalMarathi"
                else:
                    base_name = font_name.strip("/").replace("+", "_")[:40]

                # Extension
                file_ext = f".{ext}" if ext else ".ttf"
                if "cff" in font_type.lower() or "opentype" in font_type.lower():
                    file_ext = ".otf"

                output_file = output_dir / f"{base_name}{file_ext}"

                # Avoid name conflicts
                counter = 1
                original = output_file
                while output_file.exists():
                    output_file = original.with_stem(f"{original.stem}_{counter}")
                    counter += 1

                with open(output_file, "wb") as f:
                    f.write(font_data)

                saved_count += 1
                print(f"✓ Saved: {output_file.name}  ({len(font_data):,} bytes)  [Page {page_num+1}]")

            except Exception:
                continue  # Skip any problematic font

    doc.close()

    print("-" * 80)
    if saved_count > 0:
        print(f"✅ Success! {saved_count} unique font file(s) extracted to folder: '{output_dir}'")
        print("Install the SakalMarathi*.ttf file(s) and test on your garbled text.")
    else:
        print("No embedded fonts found.")
        print("Possible reasons:")
        print("1. The PDF is image-based (scanned pages)")
        print("2. Fonts are not embedded as extractable streams")
        print("\nRecommendation: Use FontForge (free) → File → Open → choose 'Extract from PDF'")


# ====================== Usage ======================
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("   python extract_with_pymupdf.py your_pdf_file.pdf")
        print("   python extract_with_pymupdf.py your_pdf_file.pdf output_folder")
        sys.exit(1)

    pdf_file = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "extracted_fonts"

    extract_sakalmarathi_with_pymupdf(pdf_file, out_dir)