import pandas as pd
from deep_translator import GoogleTranslator
import time

def translate_marathi_csv(input_csv, marathi_column, output_csv):
    """
    Reads a CSV file, translates Marathi addresses to English, 
    and saves the result to a new file.
    """
    # 1. Load the CSV file
    try:
        df = pd.read_csv(input_csv)
    except FileNotFoundError:
        print(f"Error: The file '{input_csv}' was not found.")
        return

    # 2. Initialize the Translator (Marathi 'mr' to English 'en')
    translator = GoogleTranslator(source='mr', target='en')

    def translate_text(text):
        if pd.isna(text) or str(text).strip() == "":
            return text
        try:
            # Translation process
            text = translator.translate(str(text))
            print(f"Translated: {text}")
            return text
        except Exception as e:
            print(f"Could not translate: {text}. Error: {e}")
            return text

    # 3. Apply the translation
    print(f"Starting translation of {len(df)} rows. Please wait...")
    
    # Using a loop or apply to translate. 
    # Note: For very large files, consider adding time.sleep(0.1) to avoid rate limits.
    df['eng_content'] = df[marathi_column].apply(translate_text)

    df.drop(columns=[marathi_column], inplace=True)  # Optionally drop the original Marathi column
    df.rename(columns={'eng_content': 'content'}, inplace=True)  # Rename the new
    
    # 4. Save to a new CSV file
    df.to_csv(output_csv, index=False, encoding='utf-8-sig')
    print(f"Success! Translated addresses saved to '{output_csv}'.")

# --- SETTINGS ---
INPUT_FILE = 'updated.chinchpokli.mar.csv'      # Your input file name
MARATHI_COL = 'content'        # The name of the column containing Marathi addresses
OUTPUT_FILE = 'updated.chinchpokli.eng.csv'

# Run the function
if __name__ == "__main__":
    translate_marathi_csv(INPUT_FILE, MARATHI_COL, OUTPUT_FILE)