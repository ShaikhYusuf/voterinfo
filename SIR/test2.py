import sys
from pathlib import Path
import pikepdf
import hashlib

def extract_unique_fonts_from_pdf(pdf_path: str, output_dir: str = "extracted_fonts"):
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    if not pdf_path.exists():
        print(f"Error: PDF not found: {pdf_path}")
        return

    print(f"Extracting unique fonts from: {pdf_path.name}")
    print("-" * 80)

    seen_hashes = set()      # To avoid true duplicates
    saved_count = 0

    with pikepdf.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            if page_num < 1:
                continue  # Skip first page
            resources = page.Resources
            if resources is None:
                continue

            fonts = resources.get("/Font")
            if fonts is None:
                continue

            for font_name, font_obj in fonts.items():
                try:
                    # Get FontDescriptor
                    desc = font_obj.FontDescriptor if hasattr(font_obj, "FontDescriptor") else font_obj

                    # Find font stream (FontFile2 is most common for TrueType)
                    font_file_obj = None
                    if hasattr(desc, "FontFile2"):
                        font_file_obj = desc.FontFile2
                    elif hasattr(desc, "FontFile3"):
                        font_file_obj = desc.FontFile3
                    elif hasattr(desc, "FontFile"):
                        font_file_obj = desc.FontFile

                    if font_file_obj is None:
                        continue

                    font_data = font_file_obj.read_bytes()

                    # Use hash of actual font data to detect identical fonts
                    font_hash = hashlib.md5(font_data).hexdigest()

                    if font_hash in seen_hashes:
                        continue  # Skip duplicate

                    seen_hashes.add(font_hash)

                    # Clean the name: remove prefix like AAAAAA+ and keep only SakalMarathi
                    raw_name = str(font_name).strip("/").replace("+", "_")
                    if "SakalMarathi" in raw_name or "Sakal" in raw_name:
                        clean_name = "SakalMarathi"
                    else:
                        clean_name = raw_name.split("_")[-1]   # fallback

                    # Decide extension
                    ext = ".ttf"
                    if hasattr(font_file_obj, "Subtype"):
                        subtype = str(font_file_obj.Subtype)
                        if "OpenType" in subtype or "CIDFontType0C" in subtype:
                            ext = ".otf"
                        elif "Type1" in subtype:
                            ext = ".pfb"

                    output_file = output_dir / f"{clean_name}{ext}"

                    # If same name exists, add number
                    counter = 1
                    original_file = output_file
                    while output_file.exists():
                        output_file = original_file.with_stem(f"{original_file.stem}_{counter}")
                        counter += 1

                    with open(output_file, "wb") as f:
                        f.write(font_data)

                    saved_count += 1
                    print(f"✓ Saved: {output_file.name}  ({len(font_data):,} bytes)")

                except Exception:
                    continue  # Skip any problematic font

            break  # Only process first page with fonts
        
    print("-" * 80)
    print(f"Done! {saved_count} unique font file(s) saved in folder: '{output_dir}'")
    print("Recommended: Install SakalMarathi.ttf and test on your garbled text.")


# ====================== Usage ======================
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_fonts.py your_pdf_file.pdf")
        print("       python extract_fonts.py your_pdf_file.pdf output_folder_name")
        sys.exit(1)

    pdf_file = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "extracted_fonts"

    extract_unique_fonts_from_pdf(pdf_file, out_dir)