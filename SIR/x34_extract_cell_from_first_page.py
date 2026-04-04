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
PDF_PAGE_HEIGHT_PT = 792
PT_TO_PX           = RENDER_DPI / 72.0   # 4.1667 px per point at 300 DPI

# ── Cell coordinates in PDF points ───────────────────────────────────────────
CELL_PT = {"x": 100, "y": 417, "width": 303, "height": 128}

# ── Y-axis origin ─────────────────────────────────────────────────────────────
# "bottom" → PDF spec (y=0 at page bottom)
# "top"    → screen/tool convention (y=0 at page top)
Y_ORIGIN = "bottom"

# ── OCR settings ──────────────────────────────────────────────────────────────
OCR_CONFIG = r"--oem 3 --psm 6"

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
    x, y = CELL_PT["x"], CELL_PT["y"]
    w, h = CELL_PT["width"], CELL_PT["height"]
    left  = int(x       * PT_TO_PX)
    right = int((x + w) * PT_TO_PX)
    if Y_ORIGIN == "bottom":
        top    = int((PDF_PAGE_HEIGHT_PT - y - h) * PT_TO_PX)
        bottom = int((PDF_PAGE_HEIGHT_PT - y)      * PT_TO_PX)
    else:
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
        if wb == 0 or wb == total: continue
        wf = total - wb
        sb += t * hist[t]
        v = wb * wf * (sb / wb - (s - sb) / wf) ** 2
        if v > best:
            best, thr = v, t
    arr = (arr > thr).astype(np.uint8) * 255
    return Image.fromarray(arr)


# ══════════════════════════════════════════════════════════════════════════════
#  OCR  — direct call, no nested executor
# ══════════════════════════════════════════════════════════════════════════════

def run_ocr(img, lang):
    """
    Calls Tesseract directly (no inner thread pool).
    The outer ProcessPoolExecutor provides isolation and timeout at the
    per-file level, so we don't need another layer of concurrency here.
    Returns (text, avg_confidence).
    """
    try:
        data = pytesseract.image_to_data(
            img, lang=lang, config=OCR_CONFIG,
            output_type=pytesseract.Output.DICT
        )
    except Exception as e:
        log(f"OCR failed: {e}")
        return "", 0.0

    words = [
        (data["text"][i], int(data["conf"][i]))
        for i in range(len(data["text"]))
        if str(data["text"][i]).strip() and int(data["conf"][i]) > 0
    ]
    if not words:
        return "", 0.0
    text = " ".join(w for w, _ in words)
    conf = sum(c for _, c in words) / len(words)
    return text, conf


def post_process(text):
    for pattern, replacement in CORRECTIONS:
        text = re.sub(pattern, replacement, text)
    return text.strip()


# ══════════════════════════════════════════════════════════════════════════════
#  PDF PROCESSING  — one self-contained function per worker process
# ══════════════════════════════════════════════════════════════════════════════

def process_pdf(args_tuple):
    """
    Accepts a single tuple so it works cleanly with ProcessPoolExecutor.map.
    Signature: (pdf_path, lang, poppler_path, diagnose, debug, y_origin)
    """
    pdf_path, lang, poppler_path, diagnose, debug_flag, y_origin = args_tuple

    # Re-apply globals inside the worker process (they don't inherit from main)
    global DEBUG, DIAGNOSE, Y_ORIGIN
    DEBUG    = debug_flag
    DIAGNOSE = diagnose
    Y_ORIGIN = y_origin

    if os.path.exists(TESSERACT_PATH):
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

    filename = Path(pdf_path).name
    stem     = Path(pdf_path).stem
    t0       = time.time()
    print(f"\n{filename}", flush=True)

    kwargs = {"dpi": RENDER_DPI, "first_page": 1, "last_page": 1}
    if poppler_path and os.path.exists(poppler_path):
        kwargs["poppler_path"] = poppler_path
    try:
        pages = convert_from_path(pdf_path, **kwargs)
    except Exception as e:
        log(f"PDF conversion failed: {e}")
        return {"filename": filename, "content": "", "ocr_conf": 0.0,
                "status": "error", "issues": str(e)}

    page = pages[0]
    log(f"rasterised: {page.size[0]}x{page.size[1]} px")

    box = cell_crop_box(*page.size)

    if diagnose:
        save_diagnostic(page, box, stem)

    left, top, right, bottom = box
    if right <= left or bottom <= top:
        msg = f"empty crop box {box} — check CELL_PT or Y_ORIGIN"
        log(f"ERROR: {msg}")
        return {"filename": filename, "content": "", "ocr_conf": 0.0,
                "status": "error", "issues": msg}

    cell = preprocess(page.crop(box))
    text, conf = run_ocr(cell, lang)
    text = post_process(text)

    lines   = [l.strip() for l in text.split("\n") if len(l.strip()) > 2]
    content = " | ".join(lines) if lines else text.strip()

    status, issues = "ok", ""
    if not content:
        status, issues = "error", "empty — run with --diagnose to inspect crop"
    elif conf < 40:
        status, issues = "warn", f"low confidence ({conf:.1f})"

    log(f"conf={conf:.1f}  status={status}  "
        f"text={content[:80]}{'...' if len(content) > 80 else ''}")
    log(f"done in {time.time()-t0:.1f}s")
    return {"filename": filename, "content": content,
            "ocr_conf": round(conf, 1), "status": status, "issues": issues}


# ══════════════════════════════════════════════════════════════════════════════
#  OUTPUT
# ══════════════════════════════════════════════════════════════════════════════

def save_csv(results, path):
    fields  = ["filename", "content", "ocr_conf", "status", "issues"]
    headers = ["Filename",
               "यादी भागाच्या हद्दीचा तपशील (Content)",
               "OCR Confidence", "Status", "Issues"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writerow(dict(zip(fields, headers)))
        w.writerows(results)


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    global DEBUG, DIAGNOSE, Y_ORIGIN

    ap = argparse.ArgumentParser(description="Extract cell text from voter list PDFs")
    ap.add_argument("pdfs",         nargs="*",           help="PDF file(s)")
    ap.add_argument("--folder",     default=BASE_FOLDER, help="Folder of PDFs")
    ap.add_argument("--lang",       default="mar+eng",   help="Tesseract language (default: mar+eng)")
    ap.add_argument("--out",        default="yadi_output.csv", help="Output CSV")
    ap.add_argument("--poppler",    default=None,        help="[Win] Poppler bin path")
    ap.add_argument("--tesseract",  default=None,        help="[Win] tesseract.exe path")
    ap.add_argument("--workers",    default=4, type=int, help="Parallel workers (default: 4)")
    ap.add_argument("--sequential", action="store_true", help="Process one file at a time")
    ap.add_argument("--debug",      action="store_true", help="Verbose logs")
    ap.add_argument("--diagnose",   action="store_true",
                    help="Save <stem>_page.png and <stem>_crop.png for visual inspection")
    ap.add_argument("--y-origin",   choices=["bottom", "top"], default=None,
                    help="Y coordinate origin: 'bottom' (PDF spec) or 'top' (screen/tool)")
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
        print("Usage: python extract_yadi_cell.py file.pdf [--diagnose] [--y-origin top|bottom]")
        sys.exit(1)

    if not HAS_CV2:
        print("TIP: pip install opencv-python  (+15% accuracy)\n")

    print(f"\nProcessing {len(pdf_files)} file(s)  lang={args.lang}  "
          f"dpi={RENDER_DPI}  y_origin={Y_ORIGIN}  ocr={OCR_CONFIG!r}")
    print(f"Cell (pt): x={CELL_PT['x']} y={CELL_PT['y']} "
          f"w={CELL_PT['width']} h={CELL_PT['height']}")
    if DIAGNOSE:
        print("DIAGNOSE mode ON — PNG files will be saved next to this script")

    # Build argument tuples for worker processes
    job_args = [
        (str(p), args.lang, poppler, DIAGNOSE, DEBUG, Y_ORIGIN)
        for p in pdf_files
    ]

    results = []

    if args.sequential:
        for job in job_args:
            try:
                results.append(process_pdf(job))
            except Exception as e:
                name = Path(job[0]).name
                print(f"  ERROR {name}: {e}")
                results.append({"filename": name, "content": "",
                                 "ocr_conf": 0.0, "status": "error", "issues": str(e)})
    else:
        # ProcessPoolExecutor: each worker is a separate OS process —
        # no shared GIL, no nested-executor deadlocks, Tesseract runs cleanly.
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futures = {ex.submit(process_pdf, job): job for job in job_args}
            for fut in as_completed(futures):
                job = futures[fut]
                name = Path(job[0]).name
                try:
                    results.append(fut.result(timeout=120))
                except TimeoutError:
                    print(f"  TIMEOUT {name}")
                    results.append({"filename": name, "content": "",
                                    "ocr_conf": 0.0, "status": "error",
                                    "issues": "per-file timeout"})
                except Exception as e:
                    print(f"  ERROR {name}: {e}")
                    results.append({"filename": name, "content": "",
                                    "ocr_conf": 0.0, "status": "error",
                                    "issues": str(e)})

    if not results:
        print("No results.")
        sys.exit(0)

    results.sort(key=lambda r: r["filename"])
    save_csv(results, args.out)

    ok   = sum(1 for r in results if r["status"] == "ok")
    warn = sum(1 for r in results if r["status"] == "warn")
    err  = sum(1 for r in results if r["status"] == "error")

    print(f"\n{'='*60}")
    print(f"Saved {len(results)} record(s) → {args.out}")
    print(f"ok={ok}  warn={warn}  error={err}")
    print(f"{'='*60}")
    print(f"\n{'Filename':<40} {'Conf':>6}  Status")
    print("─" * 55)
    for r in results:
        flag = "" if r["status"] == "ok" else ("!" if r["status"] == "warn" else "X")
        print(f"{r['filename']:<40} {r['ocr_conf']:>5.1f}  {flag}")
    print()


if __name__ == "__main__":
    main()
