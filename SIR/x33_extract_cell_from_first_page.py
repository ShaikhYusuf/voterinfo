import re, sys, os, csv, argparse, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

try:
    from pdf2image import convert_from_path
    import pytesseract
    from PIL import Image, ImageEnhance, ImageFilter
    import numpy as np
except ImportError:
    print("ERROR: Run: pip install pdf2image pytesseract Pillow numpy")
    sys.exit(1)

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

# ── CONFIG ─────────────────────────────────────────────────────────
TESSERACT_CONFIGS = [
    r'--oem 3 --psm 6',
    r'--oem 3 --psm 4',
    r'--oem 3 --psm 3',
]

MARATHI_CORRECTIONS = [
    (r'\s{2,}', ' '),
]

OCR_TIMEOUT = 45

# ── IMAGE UTILS ────────────────────────────────────────────────────
def pil_to_cv2(pil_img):
    return cv2.cvtColor(np.array(pil_img.convert('RGB')), cv2.COLOR_RGB2BGR)

def cv2_to_pil(cv2_img):
    return Image.fromarray(cv2.cvtColor(cv2_img, cv2.COLOR_BGR2RGB))

def preprocess_image(image, scale=2.0):
    if HAS_CV2:
        img = pil_to_cv2(image)

        # CLAHE
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        l = clahe.apply(l)
        img = cv2.cvtColor(cv2.merge((l,a,b)), cv2.COLOR_LAB2BGR)

        # Denoise
        img = cv2.bilateralFilter(img, 5, 40, 40)

        # Sharpen
        blur = cv2.GaussianBlur(img, (0,0), 2)
        img = cv2.addWeighted(img, 1.5, blur, -0.5, 0)

        image = cv2_to_pil(img)

    # Resize
    image = image.resize(
        (int(image.width*scale), int(image.height*scale)),
        Image.LANCZOS
    )

    # Binarise
    gray = np.array(image.convert('L'))
    _, binary = cv2.threshold(gray, 0, 255,
                              cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return Image.fromarray(binary)

# ── OCR ────────────────────────────────────────────────────────────
def ocr_single(image, lang, config):
    data = pytesseract.image_to_data(
        image, lang=lang, config=config,
        output_type=pytesseract.Output.DICT
    )
    words = [
        (data['text'][i], int(data['conf'][i]))
        for i in range(len(data['text']))
        if data['text'][i].strip() and int(data['conf'][i]) > 0
    ]
    text = ' '.join(w for w,_ in words)
    conf = sum(c for _,c in words)/len(words) if words else 0
    return text, conf

def ocr_ensemble(image, lang):
    best_text, best_conf = '', 0
    for cfg in TESSERACT_CONFIGS:
        text, conf = ocr_single(image, lang, cfg)
        if conf > best_conf:
            best_text, best_conf = text, conf
    return best_text, best_conf

def post_process(text):
    for p,r in MARATHI_CORRECTIONS:
        text = re.sub(p, r, text)
    return text.strip()

# ── CORE EXTRACTION ────────────────────────────────────────────────
def extract_cell_content(image, lang, use_relative=False):
    w, h = image.size

    if use_relative:
        # safer for different PDFs
        x1, y1 = int(0.10*w), int(0.30*h)
        x2, y2 = int(0.90*w), int(0.75*h)
    else:
        # your exact coordinates
        x1, y1 = 82, 264
        x2, y2 = 403, 401

    # Clamp safety
    x1, x2 = max(0,x1), min(w,x2)
    y1, y2 = max(0,y1), min(h,y2)

    crop = image.crop((x1,y1,x2,y2))
    crop = preprocess_image(crop)

    text, conf = ocr_ensemble(crop, lang)
    text = post_process(text)

    lines = [l.strip() for l in text.split('\n') if len(l.strip()) > 3]
    content = ' | '.join(lines)

    return content, conf

# ── PDF PROCESSING ─────────────────────────────────────────────────
def process_pdf(pdf_path, lang, use_relative=False):
    filename = Path(pdf_path).name

    images = convert_from_path(pdf_path, dpi=300, first_page=1, last_page=1)

    content, conf = extract_cell_content(images[0], lang, use_relative)

    return {
        "filename": filename,
        "content": content,
        "conf": round(conf,1)
    }

# ── CSV OUTPUT ─────────────────────────────────────────────────────
def save_csv(results, out):
    with open(out, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(["Content"])
        for r in results:
            writer.writerow([r["content"]])

# ── MAIN ───────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdfs", nargs="*")
    parser.add_argument("--folder")
    parser.add_argument("--lang", default="mar+eng")
    parser.add_argument("--out", default="output.csv")
    parser.add_argument("--relative", action="store_true",
                        help="Use relative coordinates")
    args = parser.parse_args()

    pdfs = args.pdfs
    if args.folder:
        pdfs += list(Path(args.folder).glob("*.pdf"))

    if not pdfs:
        print("No PDFs provided")
        return

    results = []
    for pdf in pdfs:
        try:
            results.append(process_pdf(str(pdf), args.lang, args.relative))
            print(f"✓ {pdf}")
        except Exception as e:
            print(f"✗ {pdf} → {e}")

    save_csv(results, args.out)
    print(f"\nSaved → {args.out}")

if __name__ == "__main__":
    main()