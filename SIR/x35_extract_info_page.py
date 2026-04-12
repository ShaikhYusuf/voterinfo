import re, sys, os, csv, argparse, time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from x0_settings import BASE_FOLDER

try:
    from pdf2image import convert_from_path
    import pytesseract
    from PIL import Image, ImageDraw
    import numpy as np
except ImportError:
    print("ERROR: Run:  pip install pdf2image pytesseract Pillow numpy")
    sys.exit(1)

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    print("WARNING: opencv-python not installed. Install for better accuracy:")
    print("         pip install opencv-python")

# ── Paths (Windows defaults) ──────────────────────────────────────────────────
TESSERACT_PATH = "C:/Program Files/Tesseract-OCR/tesseract.exe"
POPPLER_PATH   = "D:/poppler/Library/bin"
if os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

# ── Render settings ───────────────────────────────────────────────────────────
RENDER_DPI         = 300
PDF_PAGE_HEIGHT_PT = 842   # A4 height in points (confirmed via pdfplumber)
PDF_PAGE_WIDTH_PT  = 595   # A4 width  in points
PT_TO_PX           = RENDER_DPI / 72.0   # 4.1667 px per point at 300 DPI

# ── Target cell ───────────────────────────────────────────────────────────────
# Extracts: "यादी भाग क. 137 : 4 - मयु.घ.नं.21 ए, गनी अत्तरवाला चाळ, घेलाबाई रोड,"
#
# Coordinates measured via pdfplumber on page 1.
# pdfplumber uses Y_ORIGIN = "top"  (y=0 at TOP of page).
#
#   "यहदद" word: x0=19.6  top=61.2
#   "ररड," word: x1=269.1 bottom=69.7   (end of visible line on page 1)
#
# We use x=10 to y=58 with full page width and generous height (16 pt)
# so the entire line is captured even across different PDFs.
# ─────────────────────────────────────────────────────────────────────────────
CELL_PT = {
    "page":   2,     # PDF page number (1-based) that contains the yadi header
    "x":      5,    # left  edge in points
    "y":      50,    # top   edge in points  (measured from TOP of page)
    "width":  560,   # full page width — captures the complete line
    "height": 16,    # line height with padding  (~8 pt text + 8 pt breathing room)
}

# Y_ORIGIN must match how the coordinates above were measured.
# "top"    → y=0 at the TOP  of the page  (pdfplumber / screen convention)
# "bottom" → y=0 at the BOTTOM of the page (PDF spec / Adobe Acrobat)
Y_ORIGIN = "top"

# ── OCR settings ──────────────────────────────────────────────────────────────
# psm 7 = treat the image as a single text line  (best for a header strip)
OCR_CONFIG = r"--oem 3 --psm 7"

# ── Post-correction table ─────────────────────────────────────────────────────
CORRECTIONS = [
    (r"\|{2,}",                "|"),
    (r"(?<=[^\s])\|(?=[^\s])", " | "),
    (r"\s{2,}",                " "),
]

DEBUG    = False
DIAGNOSE = False


def log(msg):
    print(f"  {msg}", flush=True)


def dbg(msg):
    if DEBUG:
        print(f"  [DBG] {msg}", flush=True)


# ══════════════════════════════════════════════════════════════════════════════
#  COORDINATE CONVERSION
# ══════════════════════════════════════════════════════════════════════════════

def cell_crop_box(img_w, img_h):
    """
    Convert CELL_PT (PDF point coordinates) → pixel crop box for the
    rasterised page image.

    Y_ORIGIN = "top"    → y=0 at the TOP  of the page (pdfplumber/screen)
    Y_ORIGIN = "bottom" → y=0 at the BOTTOM of the page (PDF spec / Adobe)
    """
    x, y = CELL_PT["x"], CELL_PT["y"]
    w, h = CELL_PT["width"], CELL_PT["height"]

    left  = int(x       * PT_TO_PX)
    right = int((x + w) * PT_TO_PX)

    if Y_ORIGIN == "bottom":
        top    = int((PDF_PAGE_HEIGHT_PT - y - h) * PT_TO_PX)
        bottom = int((PDF_PAGE_HEIGHT_PT - y)      * PT_TO_PX)
    else:   # "top" — origin at top-left  (pdfplumber convention)
        top    = int(y       * PT_TO_PX)
        bottom = int((y + h) * PT_TO_PX)

    left, right = max(0, left),  min(right,  img_w)
    top, bottom = max(0, top),   min(bottom, img_h)

    log(f"crop (px): left={left} top={top} right={right} bottom={bottom} "
        f"size={right-left}x{bottom-top}")
    return left, top, right, bottom


# ══════════════════════════════════════════════════════════════════════════════
#  DIAGNOSTICS
# ══════════════════════════════════════════════════════════════════════════════

def save_diagnostic(page_img, box, stem):
    out_dir = Path(__file__).parent
    annotated = page_img.copy().convert("RGB")
    draw = ImageDraw.Draw(annotated)
    draw.rectangle(list(box), outline="red", width=4)
    page_path = out_dir / f"{stem}_page.png"
    annotated.save(str(page_path))
    log(f"[DIAGNOSE] full page   → {page_path}")
    crop_path = out_dir / f"{stem}_crop.png"
    page_img.crop(box).save(str(crop_path))
    log(f"[DIAGNOSE] crop region → {crop_path}")


# ══════════════════════════════════════════════════════════════════════════════
#  IMAGE PREPROCESSING
# ══════════════════════════════════════════════════════════════════════════════

def _pil_to_cv2(img):
    return cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)


def _cv2_to_pil(img):
    return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))


def preprocess(img):
    """CLAHE → bilateral denoise → unsharp mask → 2× upscale → adaptive binarise."""
    if HAS_CV2:
        try:
            cv = _pil_to_cv2(img)
            lab = cv2.cvtColor(cv, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            l = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l)
            cv = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
            cv = cv2.bilateralFilter(cv, d=5, sigmaColor=40, sigmaSpace=40)
            blurred = cv2.GaussianBlur(cv, (0, 0), sigmaX=2)
            cv = cv2.addWeighted(cv, 1.5, blurred, -0.5, 0)
            img = _cv2_to_pil(cv)
        except Exception as e:
            dbg(f"cv2 preprocess failed: {e}")

    img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)

    if HAS_CV2:
        try:
            gray = cv2.cvtColor(_pil_to_cv2(img), cv2.COLOR_BGR2GRAY)
            binary = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY, blockSize=31, C=10
            )
            return Image.fromarray(binary)
        except Exception as e:
            dbg(f"adaptive threshold failed: {e}")

    # Fallback: numpy Otsu
    arr = np.array(img.convert("L"), dtype=np.uint8)
    hist, _ = np.histogram(arr.flatten(), 256, (0, 256))
    total, s = arr.size, np.dot(np.arange(256), hist)
    sb, wb, best, thr = 0.0, 0, 0.0, 128
    for t in range(256):
        wb += hist[t]
        if wb == 0 or wb == total:
            continue
        wf = total - wb
        sb += t * hist[t]
        v = wb * wf * (sb / wb - (s - sb) / wf) ** 2
        if v > best:
            best, thr = v, t
    arr = (arr > thr).astype(np.uint8) * 255
    return Image.fromarray(arr)


# ══════════════════════════════════════════════════════════════════════════════
#  OCR — uses image_to_string to preserve line breaks
# ══════════════════════════════════════════════════════════════════════════════

def run_ocr(img, lang):
    """
    Uses image_to_string (preserves newlines) + image_to_data (confidence).
    Returns (text, avg_confidence).
    """
    try:
        text = pytesseract.image_to_string(img, lang=lang, config=OCR_CONFIG)
        data = pytesseract.image_to_data(
            img, lang=lang, config=OCR_CONFIG,
            output_type=pytesseract.Output.DICT
        )
    except Exception as e:
        log(f"OCR failed: {e}")
        return "", 0.0

    words_conf = [
        int(data["conf"][i])
        for i in range(len(data["text"]))
        if str(data["text"][i]).strip() and int(data["conf"][i]) > 0
    ]
    conf = sum(words_conf) / len(words_conf) if words_conf else 0.0
    return text, conf


def post_process(text):
    """Apply corrections and preserve multi-line structure."""
    for pattern, replacement in CORRECTIONS:
        text = re.sub(pattern, replacement, text)
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if l]
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
#  PDF PROCESSING
# ══════════════════════════════════════════════════════════════════════════════

def process_pdf(args_tuple):
    """
    Signature: (pdf_path, lang, poppler_path, diagnose, debug, y_origin)
    Renders only the target page (CELL_PT["page"]) and OCRs the header strip.
    """
    pdf_path, lang, poppler_path, diagnose, debug_flag, y_origin = args_tuple

    global DEBUG, DIAGNOSE, Y_ORIGIN
    DEBUG    = debug_flag
    DIAGNOSE = diagnose
    Y_ORIGIN = y_origin

    if os.path.exists(TESSERACT_PATH):
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

    filename    = Path(pdf_path).name
    stem        = Path(pdf_path).stem
    t0          = time.time()
    target_page = CELL_PT["page"]   # 1-based

    print(f"\n{filename}  →  extracting page {target_page}", flush=True)

    # Render only the one page we need (first_page / last_page are 1-based ints)
    kwargs = {
        "dpi":        RENDER_DPI,
        "first_page": 2   # int ← important, not a string
    }
    if poppler_path and os.path.exists(poppler_path):
        kwargs["poppler_path"] = poppler_path

    try:
        pages = convert_from_path(pdf_path, **kwargs)
    except Exception as e:
        return [{
            "filename": filename,
            "page":     target_page,
            "content":  "",
            "ocr_conf": 0.0,
            "status":   "error",
            "issues":   str(e)
        }]

    results = []

    for i, page in enumerate(pages):
        page_num = target_page + i
        print(f"  processing page {page_num} (image size: {page.size})", flush=True)

        box = cell_crop_box(*page.size)

        if diagnose:
            save_diagnostic(page, box, f"{stem}_p{page_num}")

        left, top, right, bottom = box

        if right <= left or bottom <= top:
            log(f"Skipping page {page_num}: invalid crop box — check CELL_PT")
            results.append({
                "filename": filename,
                "page":     page_num,
                "content":  "",
                "ocr_conf": 0.0,
                "status":   "error",
                "issues":   "invalid crop box"
            })
            continue

        cell = preprocess(page.crop(box))
        text, conf = run_ocr(cell, lang)
        text = post_process(text)

        if not text:
            status, issues = "empty", "no text extracted"
        elif conf < 40:
            status, issues = "warn", f"low confidence ({conf:.1f})"
        else:
            status, issues = "ok", ""

        results.append({
            "filename": filename,
            "page":     page_num,
            "content":  text,           # \n preserved; DictWriter quotes automatically
            "ocr_conf": round(conf, 1),
            "status":   status,
            "issues":   issues
        })

        preview = text.replace("\n", " | ")
        print(f"  page {page_num} done  [conf={conf:.1f}  status={status}]  → {preview!r}",
              flush=True)

    log(f"Done — {len(results)} record(s) in {time.time()-t0:.1f}s")
    return results


# ══════════════════════════════════════════════════════════════════════════════
#  OUTPUT
# ══════════════════════════════════════════════════════════════════════════════

def save_csv(results, path):
    fields = ["filename", "page", "content", "ocr_conf", "status", "issues"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(results)


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    global DEBUG, DIAGNOSE, Y_ORIGIN

    ap = argparse.ArgumentParser(
        description="Extract yadi-header line from voter-list PDFs"
    )
    ap.add_argument("pdfs",         nargs="*",                help="PDF file(s)")
    ap.add_argument("--folder",     default=BASE_FOLDER,      help="Folder of PDFs")
    ap.add_argument("--lang",       default="eng",        help="Tesseract language (default: mar+eng)")
    ap.add_argument("--out",        default="yadi_output.csv",help="Output CSV")
    ap.add_argument("--poppler",    default=None,             help="[Win] Poppler bin path")
    ap.add_argument("--tesseract",  default=None,             help="[Win] tesseract.exe path")
    ap.add_argument("--workers",    default=4, type=int,      help="Parallel workers (default: 4)")
    ap.add_argument("--sequential", action="store_true",      help="Process one file at a time")
    ap.add_argument("--debug",      action="store_true",      help="Verbose logs")
    ap.add_argument("--diagnose",   action="store_true",
                    help="Save <stem>_page.png + <stem>_crop.png for visual inspection")
    ap.add_argument("--y-origin",   choices=["bottom", "top"], default=None,
                    help="Override Y-origin: 'top' (pdfplumber) or 'bottom' (PDF spec)")
    args = ap.parse_args()

    DEBUG    = args.debug
    DIAGNOSE = args.diagnose
    if args.y_origin:
        Y_ORIGIN = args.y_origin

    if args.tesseract and os.path.exists(args.tesseract):
        pytesseract.pytesseract.tesseract_cmd = args.tesseract

    poppler = args.poppler or (POPPLER_PATH if os.path.exists(POPPLER_PATH) else None)

    pdf_files = list(args.pdfs) if args.pdfs else []
    if args.folder:
        p = Path(args.folder)
        pdf_files += sorted(set(p.glob("*.pdf")) | set(p.glob("*.PDF")))

    if not pdf_files:
        print("No PDFs found.")
        print("Usage: python extract_yadi_cell.py file.pdf [--diagnose]")
        sys.exit(1)

    if not HAS_CV2:
        print("TIP: pip install opencv-python  (+15% accuracy)\n")

    print(f"\nProcessing {len(pdf_files)} file(s)")
    print(f"  lang={args.lang}  dpi={RENDER_DPI}  y_origin={Y_ORIGIN}  ocr={OCR_CONFIG!r}")
    print(f"  Target cell: page={CELL_PT['page']}  x={CELL_PT['x']}  y={CELL_PT['y']}  "
          f"w={CELL_PT['width']}  h={CELL_PT['height']}")
    if DIAGNOSE:
        print("  DIAGNOSE mode ON — PNG files saved next to this script")

    job_args = [
        (str(p), args.lang, poppler, DIAGNOSE, DEBUG, Y_ORIGIN)
        for p in pdf_files
    ]

    results = []

    if args.sequential:
        for job in job_args:
            results.extend(process_pdf(job))
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futures = {ex.submit(process_pdf, job): job for job in job_args}
            for fut in as_completed(futures):
                try:
                    results.extend(fut.result(timeout=180))
                except Exception as e:
                    print(f"Worker failed: {e}", flush=True)

    results.sort(key=lambda r: (r["filename"], r["page"]))
    save_csv(results, args.out)

    ok    = sum(1 for r in results if r["status"] == "ok")
    warn  = sum(1 for r in results if r["status"] == "warn")
    empty = sum(1 for r in results if r["status"] == "empty")
    err   = sum(1 for r in results if r["status"] == "error")

    print(f"\n{'='*60}")
    print(f"Saved {len(results)} record(s) → {args.out}")
    print(f"ok={ok}  warn={warn}  empty={empty}  error={err}")
    print(f"{'='*60}")
    print(f"\n{'Filename':<40} {'Pg':>3} {'Conf':>5}  St  Content preview")
    print("─" * 80)
    for r in results:
        flag    = {"ok": " ", "warn": "!", "empty": "?", "error": "X"}.get(r["status"], "?")
        preview = r["content"].replace("\n", " | ")[:45]
        print(f"{r['filename']:<40} {r['page']:>3} {r['ocr_conf']:>4.1f}  {flag}   {preview}")
    print()


if __name__ == "__main__":
    main()