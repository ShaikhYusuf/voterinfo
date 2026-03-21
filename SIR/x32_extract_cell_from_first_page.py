import re, sys, os, csv, argparse, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

try:
    from pdf2image import convert_from_path
    import pytesseract
    import pandas as pd
    from PIL import ImageEnhance, ImageFilter, Image
    import numpy as np
except ImportError:
    print("ERROR: Run:  pip install pdf2image pytesseract pandas Pillow numpy")
    sys.exit(1)

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    print("WARNING: opencv-python not installed. Deskew and CLAHE disabled.")
    print("         Run: pip install opencv-python")

TESSERACT_PATH = "C:/Program Files/Tesseract-OCR/tesseract.exe"
POPPLER_PATH   = "D:/poppler/Library/bin"
if os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

# ── Timeouts ──────────────────────────────────────────────────────────────────
PDF_CONVERT_TIMEOUT = 60
OCR_TIMEOUT         = 45
PER_FILE_TIMEOUT    = 180

# ── Quality thresholds ────────────────────────────────────────────────────────
MIN_CONTENT_LENGTH  = 10
MIN_WORD_COUNT      = 2
MAX_GARBLE_RATIO    = 0.35
CONFIDENCE_FLOOR    = 40

# ── Tesseract multi-config ensemble ──────────────────────────────────────────
# We try each config and keep the result with the highest average confidence.
TESSERACT_CONFIGS = [
    r'--oem 3 --psm 6',   # uniform text block (best for full-page body text)
    r'--oem 3 --psm 4',   # single column of variable-size text
    r'--oem 3 --psm 3',   # fully automatic page segmentation
]

# Known Tesseract glyph confusions for Devanagari / Marathi + common symbols.
# Add more pairs as you discover them from your specific PDF scans.
MARATHI_CORRECTIONS = [
    (r'0(?=\d)',   'o'),    # OCR confuses digit-0 with letter-o at start of words
    (r'\|{2,}',   '|'),    # multiple pipes collapsed to one
    (r'(?<=[^\s])\|(?=[^\s])', ' | '),  # ensure pipe separators have spaces
    (r'\s{2,}',   ' '),    # collapse multiple spaces
    (r'[^\S\n]+\n', '\n'), # trailing whitespace before newline
]

DEBUG = False


def log(msg, level="INFO"):
    prefix = {"INFO": "   ", "STEP": "   >", "WARN": "   !", "ERR": "   X"}
    print(f"{prefix.get(level,'   ')} {msg}", flush=True)


def debug(msg):
    if DEBUG:
        print(f"   [DBG] {msg}", flush=True)


# ══════════════════════════════════════════════════════════════════════════════
#  IMAGE PREPROCESSING  (the main accuracy driver)
# ══════════════════════════════════════════════════════════════════════════════

def pil_to_cv2(pil_img):
    return cv2.cvtColor(np.array(pil_img.convert('RGB')), cv2.COLOR_RGB2BGR)


def cv2_to_pil(cv2_img):
    return Image.fromarray(cv2.cvtColor(cv2_img, cv2.COLOR_BGR2RGB))


def deskew(pil_img):
    """
    Detect and correct page skew using the Hough transform on binary edges.
    Even a 1-2 degree tilt causes Tesseract to split characters across 'lines',
    producing garbled output. This is the single biggest accuracy win.
    Returns deskewed PIL image (or original if deskew fails / cv2 not available).
    """
    if not HAS_CV2:
        return pil_img

    try:
        img = pil_to_cv2(pil_img)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Binarise with Otsu for edge detection
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Find bounding boxes of connected components (text blobs)
        coords = np.column_stack(np.where(binary > 0))
        if len(coords) < 100:
            return pil_img   # not enough content to estimate skew

        # Use minAreaRect on all text pixels to estimate rotation
        angle = cv2.minAreaRect(coords)[-1]

        # minAreaRect returns angle in [-90, 0]. Convert to [-45, 45] range.
        if angle < -45:
            angle = 90 + angle
        else:
            angle = angle  # already near 0

        # Skip if skew is negligible (< 0.3 deg) to avoid introducing artifacts
        if abs(angle) < 0.3:
            debug(f"Deskew: skew={angle:.2f}° — skipped (negligible)")
            return pil_img

        debug(f"Deskew: correcting {angle:.2f}°")
        h, w = img.shape[:2]
        centre = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(centre, angle, 1.0)
        rotated = cv2.warpAffine(img, M, (w, h),
                                 flags=cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_REPLICATE)
        return cv2_to_pil(rotated)
    except Exception as e:
        debug(f"Deskew failed: {e}")
        return pil_img


def apply_clahe(pil_img):
    """
    CLAHE (Contrast Limited Adaptive Histogram Equalization) normalises
    uneven illumination — shadows, dark corners, faded ink — tile by tile.
    Much better than global contrast adjustment for scanned documents.
    """
    if not HAS_CV2:
        return pil_img

    try:
        img  = pil_to_cv2(pil_img)
        lab  = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_eq  = clahe.apply(l)
        lab_eq = cv2.merge((l_eq, a, b))
        result = cv2.cvtColor(lab_eq, cv2.COLOR_LAB2BGR)
        return cv2_to_pil(result)
    except Exception as e:
        debug(f"CLAHE failed: {e}")
        return pil_img


def denoise(pil_img):
    """
    Bilateral filter: removes scanner noise while preserving sharp ink edges.
    Unlike Gaussian blur it doesn't smear glyph strokes.
    """
    if not HAS_CV2:
        return pil_img

    try:
        img    = pil_to_cv2(pil_img)
        result = cv2.bilateralFilter(img, d=5, sigmaColor=40, sigmaSpace=40)
        return cv2_to_pil(result)
    except Exception as e:
        debug(f"Denoise failed: {e}")
        return pil_img


def unsharp_mask(pil_img):
    """
    Unsharp mask sharpens character strokes without amplifying noise
    (which plain PIL SHARPEN does). Devanagari matras and vertical strokes
    benefit most.
    """
    if not HAS_CV2:
        img = pil_img.filter(ImageFilter.SHARPEN).filter(ImageFilter.SHARPEN)
        return img

    try:
        img      = pil_to_cv2(pil_img)
        blurred  = cv2.GaussianBlur(img, (0, 0), sigmaX=2)
        sharpened = cv2.addWeighted(img, 1.5, blurred, -0.5, 0)
        return cv2_to_pil(sharpened)
    except Exception as e:
        debug(f"Unsharp mask failed: {e}")
        return pil_img.filter(ImageFilter.SHARPEN)


def _otsu_threshold_np(arr):
    hist, _ = np.histogram(arr.flatten(), bins=256, range=(0, 256))
    total   = arr.size
    sum_all = np.dot(np.arange(256), hist)
    sum_b, w_b, max_var, threshold = 0.0, 0, 0.0, 128
    for t in range(256):
        w_b += hist[t]
        if w_b == 0: continue
        w_f = total - w_b
        if w_f == 0: break
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (sum_all - sum_b) / w_f
        var = w_b * w_f * (m_b - m_f) ** 2
        if var > max_var:
            max_var   = var
            threshold = t
    return threshold


def binarise(pil_img):
    """
    Otsu global binarisation → pure black-on-white.
    OpenCV's adaptive threshold (ADAPTIVE_THRESH_GAUSSIAN_C) is used when
    available because it handles uneven ink density better than global Otsu.
    """
    if HAS_CV2:
        try:
            gray  = cv2.cvtColor(pil_to_cv2(pil_img), cv2.COLOR_BGR2GRAY)
            binary = cv2.adaptiveThreshold(
                gray, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                blockSize=31,   # neighbourhood size (must be odd)
                C=10            # constant subtracted from mean
            )
            return Image.fromarray(binary)
        except Exception as e:
            debug(f"Adaptive threshold failed: {e}")

    # Fallback: numpy Otsu
    arr = np.array(pil_img.convert('L'), dtype=np.uint8)
    thr = _otsu_threshold_np(arr)
    arr = (arr > thr).astype(np.uint8) * 255
    return Image.fromarray(arr)


def preprocess_image(image, *, scale=2.0, deskew_page=False):
    """
    Full preprocessing pipeline.
    Order matters: deskew first (geometry), then lighting, then sharpening,
    then upscale, then binarise.

    deskew_page=True only for full-page images (expensive op, not needed for crops).
    """
    debug(f"Preprocess start  size={image.size}  scale={scale}  deskew={deskew_page}")

    # 1. Deskew (full page only — crops are already axis-aligned)
    if deskew_page:
        image = deskew(image)

    # 2. CLAHE — fix uneven lighting before anything else
    image = apply_clahe(image)

    # 3. Denoise — remove scanner speckle
    image = denoise(image)

    # 4. Unsharp mask — sharpen glyph edges
    image = unsharp_mask(image)

    # 5. Upscale (LANCZOS preserves stroke sharpness)
    new_w = int(image.width  * scale)
    new_h = int(image.height * scale)
    image = image.resize((new_w, new_h), Image.LANCZOS)

    # 6. Binarise
    image = binarise(image)

    debug(f"Preprocess done  output={image.size}")
    return image


# ══════════════════════════════════════════════════════════════════════════════
#  OCR — MULTI-CONFIG ENSEMBLE
# ══════════════════════════════════════════════════════════════════════════════

def _run_ocr_data(image, lang, config):
    return pytesseract.image_to_data(
        image, lang=lang, config=config,
        output_type=pytesseract.Output.DICT
    )


def ocr_single(image, lang, config, timeout=OCR_TIMEOUT):
    """Run one Tesseract config with a timeout. Returns (text, avg_conf)."""
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(_run_ocr_data, image, lang, config)
        try:
            data = fut.result(timeout=timeout)
        except TimeoutError:
            log(f"OCR timed out ({timeout}s) config={config}", "WARN")
            return '', 0.0
        except Exception as e:
            debug(f"OCR config={config} failed: {e}")
            # Fallback: try English only
            try:
                fut2 = ex.submit(_run_ocr_data, image, 'eng', config)
                data = fut2.result(timeout=timeout)
            except Exception:
                return '', 0.0

    words = [
        (data['text'][i], int(data['conf'][i]))
        for i in range(len(data['text']))
        if str(data['text'][i]).strip() and int(data['conf'][i]) > 0
    ]
    text     = ' '.join(w for w, _ in words)
    avg_conf = (sum(c for _, c in words) / len(words)) if words else 0.0
    return text, avg_conf


def ocr_ensemble(image, lang):
    """
    Run multiple Tesseract configs in parallel and return the result
    with the highest average confidence. This handles pages where a single
    PSM mode gives poor results because of layout variations.
    """
    debug(f"Ensemble OCR  configs={len(TESSERACT_CONFIGS)}")
    best_text, best_conf = '', 0.0

    with ThreadPoolExecutor(max_workers=len(TESSERACT_CONFIGS)) as ex:
        futures = {
            ex.submit(ocr_single, image, lang, cfg, OCR_TIMEOUT): cfg
            for cfg in TESSERACT_CONFIGS
        }
        for fut in as_completed(futures):
            cfg = futures[fut]
            try:
                text, conf = fut.result()
                debug(f"  config={cfg}  conf={conf:.1f}  len={len(text)}")
                if conf > best_conf:
                    best_conf = conf
                    best_text = text
            except Exception as e:
                debug(f"  config={cfg} error: {e}")

    debug(f"Ensemble best conf={best_conf:.1f}")
    return best_text, best_conf


# ══════════════════════════════════════════════════════════════════════════════
#  POST-PROCESSING
# ══════════════════════════════════════════════════════════════════════════════

def post_process(text):
    """
    Apply Marathi-aware corrections to fix common OCR glyph confusions.
    These are deterministic string fixes derived from the MARATHI_CORRECTIONS
    table at the top. Add pairs as you identify recurring errors in your data.
    """
    for pattern, replacement in MARATHI_CORRECTIONS:
        text = re.sub(pattern, replacement, text)
    return text.strip()


# ══════════════════════════════════════════════════════════════════════════════
#  CORE EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

def extract_yadi_bhag_no(images, lang):
    debug("Extracting Yadi Bhag No.")
    pages_to_check = images[:2] if len(images) >= 2 else images
    for img in reversed(pages_to_check):
        pre = preprocess_image(img, scale=1.5, deskew_page=True)
        text, _ = ocr_single(pre, lang, TESSERACT_CONFIGS[0], OCR_TIMEOUT)
        for line in text.split('\n')[:8]:
            m = re.search(r'0{1,2}(\d{3,4})\b', line)
            if m:
                raw = m.group(0)
                num = raw.lstrip('0') or '0'
                return num.zfill(4)
    return ''


def find_cell_boundaries(df, img_height):
    label = df[
        (df['left'] < 700) &
        (df['text'].str.lower().str.contains(r'areal|sera|sea|yadi|tart', regex=True))
    ]
    y_top = int(label['top'].min()) + 45 if not label.empty else int(img_height * 0.315)
    sec3  = df[df['text'].str.match(r'^0\d{2}$') & (df['top'] > img_height * 0.50)]
    y_bottom = int(sec3['top'].min()) - 50 if not sec3.empty else int(img_height * 0.56)
    if y_bottom <= y_top:
        y_bottom = y_top + int(img_height * 0.20)
    debug(f"Boundaries y_top={y_top}  y_bottom={y_bottom}")
    return y_top, y_bottom


def extract_cell_content(image, lang):
    w, h = image.size
    debug(f"extract_cell_content {w}x{h}")

    log("Step 1/4: Deskewing full page...", "STEP")
    page_deskewed = deskew(image)

    log("Step 2/4: Detecting cell boundaries...", "STEP")
    pre_full = preprocess_image(page_deskewed, scale=1.0, deskew_page=False)
    raw_data = pytesseract.image_to_data(
        pre_full, lang=lang, output_type=pytesseract.Output.DICT,
        config=TESSERACT_CONFIGS[0]
    )
    df = pd.DataFrame(raw_data)
    df = df[(df['conf'] > 15) & (df['text'].str.strip() != '')]
    y_top, y_bottom = find_cell_boundaries(df, h)

    log("Step 3/4: Preprocessing cell crop...", "STEP")
    crop_raw = page_deskewed.crop((420, y_top, w - 80, y_bottom))
    crop     = preprocess_image(crop_raw, scale=2.0, deskew_page=False)

    log("Step 4/4: Running ensemble OCR...", "STEP")
    text, avg_conf = ocr_ensemble(crop, lang)

    text = post_process(text)
    lines   = [l.strip() for l in text.split('\n') if len(l.strip()) > 3]
    content = ' | '.join(lines)
    content = re.sub(r'\s{2,}', ' ', content).strip()
    return content, avg_conf, y_top, y_bottom


# ══════════════════════════════════════════════════════════════════════════════
#  QUALITY ASSESSMENT
# ══════════════════════════════════════════════════════════════════════════════

def assess_quality(text, avg_conf):
    issues = []
    if not text.strip():
        return ['Empty extraction'], 'error'
    if len(text.strip()) < MIN_CONTENT_LENGTH:
        issues.append(f"Very short text ({len(text.strip())} chars)")
    if len(text.split()) < MIN_WORD_COUNT:
        issues.append(f"Too few words ({len(text.split())})")
    total = len(text.replace(' ', ''))
    if total > 0:
        garbled = sum(
            1 for c in text
            if c != ' ' and not c.isdigit()
            and not ('A' <= c <= 'z')
            and not ('\u0900' <= c <= '\u097F')
            and c not in '|.,/-:()'
        )
        ratio = garbled / total
        if ratio > MAX_GARBLE_RATIO:
            issues.append(f"High garble ratio ({ratio:.0%})")
    if avg_conf < CONFIDENCE_FLOOR:
        issues.append(f"Low OCR confidence ({avg_conf:.1f}/100)")
    severity = 'ok'
    if issues:
        severity = 'error' if len(issues) >= 2 or avg_conf < 20 else 'warn'
    return issues, severity


# ══════════════════════════════════════════════════════════════════════════════
#  PDF PROCESSING
# ══════════════════════════════════════════════════════════════════════════════

def _error_row(filename, reason, yadi_bhag_no=''):
    return [{'filename': filename, 'page_no': 1, 'yadi_bhag_no': yadi_bhag_no,
             'content': '', 'ocr_conf': 0.0, 'status': 'error', 'issues': reason}]


def process_pdf(pdf_path, lang, poppler_path=None):
    filename = Path(pdf_path).name
    t_start  = time.time()
    print(f"\n--- {filename}", flush=True)

    log("Converting PDF to images...", "STEP")
    kwargs = {'dpi': 300, 'first_page': 1, 'last_page': 2}
    if poppler_path and os.path.exists(poppler_path):
        kwargs['poppler_path'] = poppler_path

    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(convert_from_path, pdf_path, **kwargs)
            try:
                images = fut.result(timeout=PDF_CONVERT_TIMEOUT)
            except TimeoutError:
                log(f"PDF conversion timed out after {PDF_CONVERT_TIMEOUT}s", "ERR")
                return _error_row(filename, "PDF conversion timed out")
    except Exception as e:
        log(f"Could not open PDF: {e}", "ERR")
        return _error_row(filename, f"PDF open error: {e}")

    log(f"Converted {len(images)} page(s) in {time.time()-t_start:.1f}s")

    log("Extracting Yadi Bhag No....", "STEP")
    yadi_bhag_no = extract_yadi_bhag_no(images, lang)
    img_p1 = images[0]
    w, h   = img_p1.size
    log(f"Page size: {w}x{h}px  Yadi Bhag: {yadi_bhag_no or '(not found)'}")

    try:
        content, avg_conf, y_top, y_bottom = extract_cell_content(img_p1, lang)
    except Exception as e:
        log(f"Cell extraction failed: {e}", "ERR")
        return _error_row(filename, f"Cell extraction error: {e}", yadi_bhag_no)

    issues, severity = assess_quality(content, avg_conf)
    elapsed = time.time() - t_start
    log(f"Cell region: y={y_top}-{y_bottom}")
    log(f"OCR conf   : {avg_conf:.1f}/100")
    log(f"Content    : {content[:100]}{'...' if len(content)>100 else ''}")
    log(f"Done in {elapsed:.1f}s  status={severity}")
    if issues:
        log(f"{'!' if severity=='warn' else 'X'} {'; '.join(issues)}", "WARN")

    return [{'filename': filename, 'page_no': 1, 'yadi_bhag_no': yadi_bhag_no,
             'content': content, 'ocr_conf': round(avg_conf, 1),
             'status': severity, 'issues': '; '.join(issues)}]


# ══════════════════════════════════════════════════════════════════════════════
#  OUTPUT
# ══════════════════════════════════════════════════════════════════════════════

def save_csv(results, output_path):
    fieldnames = ['filename','page_no','yadi_bhag_no','content','ocr_conf','status','issues']
    headers    = ['Filename','Page No.',
                  'यादी भाग क्रमांक (Yadi Bhag No.)',
                  'यादी भागाच्या हद्दीचा तपशील (Content)',
                  'OCR Confidence','Status','Issues (manual review needed)']
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writerow(dict(zip(fieldnames, headers)))
        writer.writerows(results)


def save_review_csv(results, output_path):
    flagged = [r for r in results if r['status'] != 'ok']
    if not flagged:
        print("\nAll rows passed quality checks — no review file needed.")
        return
    save_csv(flagged, output_path)
    print(f"\n{len(flagged)} row(s) flagged for manual review -> {output_path}")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    global DEBUG

    parser = argparse.ArgumentParser(
        description="Extract yadi bhagachya haddichya tapsil from voter list PDFs"
    )
    parser.add_argument("pdfs",         nargs="*",                     help="PDF file(s)")
    parser.add_argument("--folder",     default=None,                  help="Folder of PDFs")
    parser.add_argument("--lang",       default="mar+eng",             help="OCR language (default: mar+eng)")
    parser.add_argument("--out",        default="yadi_cell_index.csv", help="Output CSV (all rows)")
    parser.add_argument("--review",     default="yadi_review.csv",     help="Output CSV (flagged rows only)")
    parser.add_argument("--poppler",    default=None,                  help="[Win] Poppler bin path")
    parser.add_argument("--tesseract",  default=None,                  help="[Win] tesseract.exe path")
    parser.add_argument("--workers",    default=2, type=int,           help="Parallel workers (default: 2)")
    parser.add_argument("--debug",      action="store_true",           help="Verbose step-by-step logs")
    parser.add_argument("--sequential", action="store_true",           help="Process one file at a time")
    args = parser.parse_args()

    DEBUG = args.debug

    if args.tesseract and os.path.exists(args.tesseract):
        pytesseract.pytesseract.tesseract_cmd = args.tesseract

    poppler = args.poppler or (POPPLER_PATH if os.path.exists(POPPLER_PATH) else None)

    pdf_files = list(args.pdfs) if args.pdfs else []
    if args.folder:
        folder = Path(args.folder)
        pdf_files += sorted(set(folder.glob("*.pdf")) | set(folder.glob("*.PDF")))

    if not pdf_files:
        print("No PDFs found.")
        print("Usage: python extract_yadi_cell.py myfile.pdf [--debug] [--sequential]")
        sys.exit(1)

    if not HAS_CV2:
        print("\nTIP: Install opencv-python for +15-20% accuracy:")
        print("     pip install opencv-python\n")

    print(f"\nProcessing {len(pdf_files)} PDF(s) | lang={args.lang} | workers={args.workers}")
    if args.debug:      print("  Debug mode ON")
    if args.sequential: print("  Sequential mode ON")

    all_results = []

    if args.sequential:
        for pdf in pdf_files:
            try:
                all_results.extend(process_pdf(str(pdf), args.lang, poppler))
            except Exception as e:
                print(f"  Unhandled error for {pdf}: {e}")
                all_results.extend(_error_row(Path(pdf).name, str(e)))
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(process_pdf, str(pdf), args.lang, poppler): pdf
                for pdf in pdf_files
            }
            for future in as_completed(futures):
                pdf = futures[future]
                try:
                    all_results.extend(future.result(timeout=PER_FILE_TIMEOUT))
                except TimeoutError:
                    print(f"  {Path(pdf).name} exceeded {PER_FILE_TIMEOUT}s — skipped")
                    all_results.extend(_error_row(Path(pdf).name, f"Per-file timeout ({PER_FILE_TIMEOUT}s)"))
                except Exception as e:
                    print(f"  Error processing {pdf}: {e}")
                    all_results.extend(_error_row(Path(pdf).name, str(e)))

    if not all_results:
        print("\nNo results extracted.")
        sys.exit(0)

    all_results.sort(key=lambda x: x['filename'])
    save_csv(all_results, args.out)
    save_review_csv(all_results, args.review)

    ok_c   = sum(1 for r in all_results if r['status'] == 'ok')
    warn_c = sum(1 for r in all_results if r['status'] == 'warn')
    err_c  = sum(1 for r in all_results if r['status'] == 'error')

    print(f"\n{'='*70}")
    print(f"Done. {len(all_results)} record(s) -> {args.out}")
    print(f"  ok={ok_c}  warn={warn_c}  error={err_c}")
    print(f"{'='*70}")
    print(f"\n{'Filename':<35} {'Bhag':>6}  {'Conf':>6}  Status")
    print(f"{'─'*60}")
    for r in all_results:
        flag = '' if r['status']=='ok' else ('!' if r['status']=='warn' else 'X')
        print(f"{r['filename']:<35} {r['yadi_bhag_no']:>6}  {r['ocr_conf']:>5.1f}  {flag}")
    print()


if __name__ == "__main__":
    main()