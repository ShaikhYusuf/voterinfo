import os
import easyocr
import pandas as pd
from pdf2image import convert_from_path
import numpy as np

# 1. CHANGE THIS to your extracted Poppler bin folder
POPPLER_PATH = r'test/test2/Release-25.12.0-0/poppler-25.12.0/Library/bin' 

# Initialize OCR
reader = easyocr.Reader(['mr', 'en'], gpu=False) # gpu=False stops the CUDA warning

input_folder = 'test/test2'
output_folder = 'extracted_data_ocr'

if not os.path.exists(output_folder):
    os.makedirs(output_folder)

def process_pdf_with_ocr(pdf_path, filename):
    print(f"Processing: {filename}...")
    try:
        # Pass poppler_path here
        pages = convert_from_path(pdf_path, 300, poppler_path=POPPLER_PATH)
        
        all_data = []
        for i, page in enumerate(pages):
            if  i == 3:
                img_np = np.array(page)
                results = reader.readtext(img_np)
                
                for (bbox, text, prob) in results:
                    top_y = bbox[0][1] 
                    all_data.append({'text': text, 'y': top_y, 'page': i+1})

        if all_data:
            df = pd.DataFrame(all_data)
            csv_path = os.path.join(output_folder, f"{filename.replace('.pdf', '')}.csv")
            df.to_csv(csv_path, index=False, encoding='utf-8-sig')
            print(f"Done: {csv_path}")

    except Exception as e:
        print(f"Error processing {filename}: {e}")

# Run
for file in os.listdir(input_folder):
    if file.endswith(".pdf"):
        process_pdf_with_ocr(os.path.join(input_folder, file), file)