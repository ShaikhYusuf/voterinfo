# Command to use convert2002.py
python convert2002.py D:/arif/SIR/test-mumbai/000-Testing.pdf
python convert2002.py test-mumbai/000-Testing.pdf --lang mar+eng --out output.csv


python convert2002.py D:/arif/SIR/test-mumbai/000-Testing.pdf
    --poppler "D:\poppler\Library\bin" 
    --tesseract "C:\Program Files\Tesseract-OCR\tesseract.exe" 
    --out voters_2002.csv


python convert2002.py D:/arif/SIR/test-mumbai/000-Testing.pdf --lang mar+eng --dpi 500 --out voters_2002.csv

python x3_extract_cell_from_first_page.py --folder nagpada

# https://www.pdf-coordinates.com/
CELL_PT = {"x": 100, "y": 417, "width": 303, "height": 128} # Each page for v
CELL_PT = {"page":1,"x":15,"y":765,"width":560,"height":33}

# Step 1: Try direct text extraction with pdfplumber (it extracts the broken chars)
# Step 2: Apply a SakalMarathi → Unicode conversion using the known ISFOC mapping table
# Download: https://github.com/cosmicpotato137/font-converters (SakalMarathi converter)
# OR use the Maharashtra gov's own converter tool

# If you must use OCR, the only real improvement is:
# 1. Use google-cloud-vision API (handles Devanagari excellently)
# 2. OR use Azure Computer Vision OCR
# 3. OR install the SakalMarathi-to-Unicode font converter and process the PDF text layer

wget -O lang_data/mar.traineddata https://github.com/tesseract-ocr/tessdata/raw/main/mar.traineddata

curl -L -o lang_data/mar.traineddata https://github.com/tesseract-ocr/tessdata/raw/main/mar.traineddata

curl -L -o lang_data/eng.traineddata https://github.com/tesseract-ocr/tessdata/raw/main/eng.traineddata