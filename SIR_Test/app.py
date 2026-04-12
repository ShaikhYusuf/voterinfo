import csv
import os
import cv2
import numpy as np
from pdf2image import convert_from_path, pdfinfo_from_path
from paddleocr import PaddleOCR

# -------------------------------
# INIT OCR (load once)
# -------------------------------
ocr = PaddleOCR(
    use_angle_cls=True,
    lang='hi'   # Hindi works well for Marathi
)

# -------------------------------
# OCR FUNCTION
# -------------------------------
def extract_info_from_page(each_page, input_DPI, input_CELL_PT):
    page_img = np.array(each_page)

    # Convert PDF points → pixels
    scale = input_DPI / 72.0
    x = int(input_CELL_PT["x"] * scale)
    y = int(input_CELL_PT["y"] * scale)
    w = int(input_CELL_PT["width"] * scale)
    h = int(input_CELL_PT["height"] * scale)

    crop = page_img[y:y+h, x:x+w]

    # -------------------------------
    # Preprocess (important change)
    # -------------------------------
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    # Resize → improves OCR a lot
    processed = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

    # Optional slight denoise
    processed = cv2.GaussianBlur(processed, (3,3), 0)

    # -------------------------------
    # OCR (PaddleOCR)
    # -------------------------------
    result = ocr.ocr(processed, cls=True)

    text = ""
    if result and result[0]:
        text = " ".join([line[1][0] for line in result[0]])

    return text


# -------------------------------
# MAIN
# -------------------------------
if __name__ == "__main__":

    INPUT_FOLDER = "list2025"
    OUTPUT_CSV = "yaadi_output.csv"

    DPI = 400
    CELL_PT = {
        "x": 5,
        "y": 55,
        "width": 560,
        "height": 25,   # 🔥 increased (important)
    }

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "page", "content"])

        for file in os.listdir(INPUT_FOLDER):
            if not file.lower().endswith(".pdf"):
                continue

            pdf_path = os.path.join(INPUT_FOLDER, file)
            print(f"\nProcessing file =================> {file}")

            total_pages = pdfinfo_from_path(pdf_path)["Pages"]
            last_input = ""

            for page_num in range(2, total_pages + 1):

                pages = convert_from_path(
                    pdf_path,
                    dpi=DPI,
                    first_page=page_num,
                    last_page=page_num
                )

                each_page = pages[0]

                text = extract_info_from_page(each_page, DPI, CELL_PT)
                text = text.strip().replace("\n", " ")

                if not text or text == last_input:
                    continue

                last_input = text

                print(f"Page {page_num}: {text}")
                writer.writerow([file, page_num, text])

    print("\n✅ CSV saved to:", OUTPUT_CSV)