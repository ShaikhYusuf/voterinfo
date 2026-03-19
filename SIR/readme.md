# Command to use convert2002.py
python convert2002.py D:/arif/SIR/test-mumbai/000-Testing.pdf
python convert2002.py test-mumbai/000-Testing.pdf --lang mar+eng --out output.csv


python convert2002.py D:/arif/SIR/test-mumbai/000-Testing.pdf
    --poppler "D:\poppler\Library\bin" 
    --tesseract "C:\Program Files\Tesseract-OCR\tesseract.exe" 
    --out voters_2002.csv


python convert2002.py D:/arif/SIR/test-mumbai/000-Testing.pdf --lang mar+eng --dpi 500 --out voters_2002.csv

python x3_extract_cell_from_first_page.py --folder nagpada