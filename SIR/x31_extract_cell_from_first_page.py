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

TESSERACT_PATH = "C:/Program Files/Tesseract-OCR/tesseract.exe"
POPPLER_PATH   = "D:/poppler/Library/bin"
if os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

# ── Timeouts (seconds) ────────────────────────────────────────────────────────
PDF_CONVERT_TIMEOUT = 60
OCR_TIMEOUT         = 45
PER_FILE_TIMEOUT    = 120

# ── Quality thresholds ────────────────────────────────────────────────────────
MIN_CONTENT_LENGTH  = 10
MIN_WORD_COUNT      = 2
MAX_GARBLE_RATIO    = 0.35
CONFIDENCE_FLOOR    = 40

DEBUG = False


def log(msg, level="INFO"):
    prefix = {"INFO": "   ", "STEP": "   🔹", "WARN": "   ⚠️ ", "ERR": "   ❌"}
    print(f"{prefix.get(level,'   ')} {msg}", flush=True)


def debug(msg):
    if DEBUG:
        print(f"   [DBG] {msg}", flush=True)


# ── Safe OCR with timeout ─────────────────────────────────────────────────────

def _run_ocr_data(image, lang, config):
    return pytesseract.image_to_data(
        image, lang=lang, config=config,
        output_type=pytesseract.Output.DICT
    )


def ocr_with_timeout(image, lang, config='--oem 3 --psm 6', timeout=OCR_TIMEOUT):
    debug(f"Starting OCR  lang={lang}  img={image.size}")
    with ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(_run_ocr_data, image, lang, config)
        try:
            data = future.result(timeout=timeout)
        except TimeoutError:
            log(f"OCR timed out after {timeout}s — skipping region", "WARN")
            return '', 0.0
        except Exception as e:
            debug(f"OCR lang={lang} failed ({e}), retrying with eng")
            try:
                f2 = ex.submit(_run_ocr_data, image, 'eng', config)
                data = f2.result(timeout=timeout)
            except Exception as e2:
                log(f"OCR fallback also failed: {e2}", "WARN")
                return '', 0.0

    words = [
        (data['text'][i], int(data['conf'][i]))
        for i in range(len(data['text']))
        if str(data['text'][i]).strip() and int(data['conf'][i]) > 0
    ]
    text     = ' '.join(w for w, _ in words)
    avg_conf = (sum(c for _, c in words) / len(words)) if words else 0.0
    debug(f"OCR done  words={len(words)}  conf={avg_conf:.1f}")
    return text, avg_conf


# ── Image preprocessing ───────────────────────────────────────────────────────

def _otsu_threshold(arr):
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


def preprocess_image(image, *, scale=2.0, sharpen=True):
    debug(f"Preprocessing  scale={scale}  input={image.size}")
    img = image.resize((int(image.width*scale), int(image.height*scale)), Image.LANCZOS)
    img = img.convert('L')
    img = ImageEnhance.Contrast(img).enhance(2.2)
    if sharpen:
        img = img.filter(ImageFilter.SHARPEN)
        img = img.filter(ImageFilter.SHARPEN)
    arr = np.array(img, dtype=np.uint8)
    thr = _otsu_threshold(arr)
    arr = (arr > thr).astype(np.uint8) * 255
    debug(f"Preprocessing done  otsu={thr}")
    return Image.fromarray(arr)


# ── Core extraction ───────────────────────────────────────────────────────────

def extract_yadi_bhag_no(images, lang):
    debug("Extracting Yadi Bhag No.")
    pages_to_check = images[:2] if len(images) >= 2 else images
    for img in reversed(pages_to_check):
        pre  = preprocess_image(img, scale=1.5, sharpen=False)
        text, _ = ocr_with_timeout(pre, lang, timeout=OCR_TIMEOUT)
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
    debug(f"Boundaries  y_top={y_top}  y_bottom={y_bottom}")
    return y_top, y_bottom


def extract_cell_content(image, lang):
    w, h = image.size
    debug(f"extract_cell_content  {w}x{h}")

    log("Step 1/3: Detecting cell boundaries...", "STEP")
    pre_full = preprocess_image(image, scale=1.0, sharpen=False)
    raw_data = pytesseract.image_to_data(
        pre_full, lang=lang, output_type=pytesseract.Output.DICT,
        config='--oem 3 --psm 6'
    )
    df = pd.DataFrame(raw_data)
    df = df[(df['conf'] > 15) & (df['text'].str.strip() != '')]
    y_top, y_bottom = find_cell_boundaries(df, h)

    log("Step 2/3: Cropping and preprocessing cell region...", "STEP")
    crop_raw = image.crop((420, y_top, w - 80, y_bottom))
    crop     = preprocess_image(crop_raw, scale=2.0, sharpen=True)

    log("Step 3/3: Running OCR on cell...", "STEP")
    text, avg_conf = ocr_with_timeout(crop, lang, timeout=OCR_TIMEOUT)

    lines   = [l.strip() for l in text.split('\n') if len(l.strip()) > 3]
    content = ' | '.join(lines)
    content = re.sub(r'\s{2,}', ' ', content).strip()
    return content, avg_conf, y_top, y_bottom


# ── Quality assessment ────────────────────────────────────────────────────────

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


# ── PDF processing ────────────────────────────────────────────────────────────

def _error_row(filename, reason, yadi_bhag_no=''):
    return [{'filename': filename, 'page_no': 1, 'yadi_bhag_no': yadi_bhag_no,
             'content': '', 'ocr_conf': 0.0, 'status': 'error', 'issues': reason}]


def process_pdf(pdf_path, lang, poppler_path=None):
    filename = Path(pdf_path).name
    t_start  = time.time()
    print(f"\n📄 {filename}", flush=True)

    log("Converting PDF to images...", "STEP")
    kwargs = {'dpi': 300, 'first_page': 1, 'last_page': 1}
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

    log(f"Converted {len(images)} page(s) in {time.time()-t_start:.1f}s", "STEP")

    log("Extracting Yadi Bhag No....", "STEP")
    yadi_bhag_no = extract_yadi_bhag_no(images, lang)
    img_p1 = images[0]
    w, h   = img_p1.size
    log(f"Page size: {w}x{h}px   Yadi Bhag: {yadi_bhag_no or '(not found)'}")

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
        log(f"{'⚠️' if severity=='warn' else '❌'} {'; '.join(issues)}", "WARN")

    return [{'filename': filename, 'page_no': 1, 'yadi_bhag_no': yadi_bhag_no,
             'content': content, 'ocr_conf': round(avg_conf,1),
             'status': severity, 'issues': '; '.join(issues)}]


# ── Output ────────────────────────────────────────────────────────────────────

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
        print("\n✅ All rows passed quality checks — no review file needed.")
        return
    save_csv(flagged, output_path)
    print(f"\n🔎 {len(flagged)} row(s) flagged for manual review → {output_path}")


# ── Main ──────────────────────────────────────────────────────────────────────

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
    parser.add_argument("--sequential", action="store_true",           help="Process one file at a time (safer)")
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

    print(f"\n🔍 Processing {len(pdf_files)} PDF(s) | lang={args.lang} | workers={args.workers}")
    if args.debug:      print("   🐛 Debug mode ON")
    if args.sequential: print("   🔁 Sequential mode ON")

    all_results = []

    if args.sequential:
        for pdf in pdf_files:
            try:
                all_results.extend(process_pdf(str(pdf), args.lang, poppler))
            except Exception as e:
                print(f"   ❌ Unhandled error for {pdf}: {e}")
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
                    print(f"   ❌ {Path(pdf).name} exceeded {PER_FILE_TIMEOUT}s — skipped")
                    all_results.extend(_error_row(Path(pdf).name, f"Per-file timeout ({PER_FILE_TIMEOUT}s)"))
                except Exception as e:
                    print(f"   ❌ Error processing {pdf}: {e}")
                    all_results.extend(_error_row(Path(pdf).name, str(e)))

    if not all_results:
        print("\n⚠️  No results extracted.")
        sys.exit(0)

    all_results.sort(key=lambda x: x['filename'])
    save_csv(all_results, args.out)
    save_review_csv(all_results, args.review)

    ok_c   = sum(1 for r in all_results if r['status'] == 'ok')
    warn_c = sum(1 for r in all_results if r['status'] == 'warn')
    err_c  = sum(1 for r in all_results if r['status'] == 'error')

    print(f"\n{'='*70}")
    print(f"✅ {len(all_results)} record(s) saved → {args.out}")
    print(f"   ok={ok_c}  warn={warn_c}  error={err_c}")
    print(f"{'='*70}")
    print(f"\n{'Filename':<35} {'Bhag':>6}  {'Conf':>6}  Status")
    print(f"{'─'*60}")
    for r in all_results:
        flag = '' if r['status']=='ok' else ('⚠️' if r['status']=='warn' else '❌')
        print(f"{r['filename']:<35} {r['yadi_bhag_no']:>6}  {r['ocr_conf']:>5.1f}  {flag}")
    print()


if __name__ == "__main__":
    main()