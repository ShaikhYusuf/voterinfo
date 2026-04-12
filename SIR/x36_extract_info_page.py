import csv
import os
import cv2
import numpy as np
from pdf2image import convert_from_path, pdfinfo_from_path
import math
import pytesseract

def extract_info_from_page_old1(each_page, input_DPI, input_CELL_PT):
    page_img = np.array(each_page)

    # Convert PDF points → pixels
    scale = input_DPI / 72.0
    x = int(input_CELL_PT["x"] * scale)
    y = int(input_CELL_PT["y"] * scale)
    w = int(input_CELL_PT["width"] * scale)
    h = int(input_CELL_PT["height"] * scale)

    # PDF origin is TOP-left (as per your input)
    crop = page_img[y:y+h, x:x+w]

    # -------------------------------
    # 2. Preprocess
    # -------------------------------

    # Grayscale
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    # Adaptive threshold
    th = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31, 15
    )

    _, th = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
    processed = cv2.bitwise_not(th)
    
    # -------------------------------
    # 3. OCR (PaddleOCR)
    # -------------------------------
    custom_config = r'--oem 1 --psm 6'
    text = pytesseract.image_to_string(
        processed,
        lang='eng+mar',   # Marathi not always available → hin works well
        config=custom_config
    )
    # -------------------------------
    # 4. Post-processing (Devanagari fixes)
    # -------------------------------

    def fix_matra(text):
        # Fix common misplaced 'ि'
        text = text.replace(" ि", "ि")
        # Add more rules as needed
        return text

    def dictionary_correction(text, word_list):
        corrected = []
        for word in text.split():
            if word in word_list:
                corrected.append(word)
            else:
                # naive closest match
                corrected.append(word)  # placeholder
        return " ".join(corrected)

    text = fix_matra(text)
    # cv2.imshow("Cropped", crop)
    # cv2.imshow("Processed", processed)
    # cv2.waitKey(0)
    # cv2.destroyAllWindows()
    return text

def extract_info_from_page(each_page, input_DPI, input_CELL_PT):
    TARGET_TEXT = "यादी भाग क्र."
    MAX_RETRIES = 3

    page_img = np.array(each_page)

    scale = input_DPI / 72.0
    x = int(input_CELL_PT["x"] * scale)
    y = int(input_CELL_PT["y"] * scale)
    w = int(input_CELL_PT["width"] * scale)
    h = int(input_CELL_PT["height"] * scale)

    crop = page_img[y:y+h, x:x+w]

    def fix_matra(text):
        return text.replace(" ि", "ि").strip()

    best_text = ""
    best_conf = 0

    for attempt in range(MAX_RETRIES):

        # -------------------------------
        # Preprocessing variations
        # -------------------------------
        # Grayscale
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

        # Adaptive threshold
        th = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            31, 15
        )

        _, th = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
        processed = cv2.bitwise_not(th)

        # -------------------------------
        # OCR with confidence
        # -------------------------------
        custom_config = r'--oem 1 --psm 6'
        data = pytesseract.image_to_data(
            processed,
            lang='eng+mar',
            config=custom_config,
            output_type=pytesseract.Output.DICT
        )

        words = []
        confidences = []

        for i in range(len(data["text"])):
            word = data["text"][i].strip()
            conf = int(data["conf"][i])

            if word:
                words.append(word)
                if conf > 0:
                    confidences.append(conf)

        text = fix_matra(" ".join(words))
        # cv2.imshow("Cropped", crop)
        # cv2.imshow("Processed", processed)
        # cv2.waitKey(0)
        # cv2.destroyAllWindows()

        # average confidence
        avg_conf = int(sum(confidences) / len(confidences)) if confidences else 0

        # keep best
        if avg_conf > best_conf:
            best_conf = avg_conf
            best_text = text

        # early stop if good enough + contains target
        if TARGET_TEXT in text and avg_conf > 80:
            break

    return best_text, best_conf

# -------------------------------
# MAIN
# -------------------------------
if __name__ == "__main__":

    INPUT_FOLDER = "list_211"   # <-- pass your folder here
    OUTPUT_CSV = "yaadi_output.csv"

    DPI = 400
    CELL_PT = {
        "x": 5,
        "y": 55,
        "width": 560,
        "height": 15,
    }

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "page", "content", "confidence"])

        # iterate all PDFs
        for file in os.listdir(INPUT_FOLDER):
            if not file.lower().endswith(".pdf"):
                continue

            pdf_path = os.path.join(INPUT_FOLDER, file)
            print(f"\nProcessing file =================> {file}")

            total_pages = pdfinfo_from_path(pdf_path)["Pages"]
            last_input = ""

            # iterate all pages of the pdf
            for page_num in range(2, total_pages + 1):

                pages = convert_from_path(
                    pdf_path,
                    dpi=DPI,
                    first_page=page_num,
                    last_page=page_num
                )

                each_page = pages[0]
                text, confidence = extract_info_from_page(each_page, DPI, CELL_PT)
                text = text.strip().replace("\n", " ")
                if not text or \
                    text == last_input:
                    continue

                last_input = text
                print(f"Page {page_num}: {text}")
                writer.writerow([file, page_num, text, confidence])

    print("\n✅ CSV saved to:", OUTPUT_CSV)