import csv
import re
import os
from postal.expand import expand_address
from postal.parser import parse_address

# --- CONFIGURATION ---
INPUT_FILE = "updated.chinchpokli.eng.csv"
FILENAME = os.path.basename(INPUT_FILE)
OUTPUT_FILE = f"updated2.{FILENAME}"

def split_english_markers(text):
    """
    Splits address by English markers like a), b), c) or 1 a), 1 b).
    """
    # Regex for: optional digit + optional space + letter a-z + closing bracket
    marker_pattern = r'(\d?\s*[a-z]\))'
    
    parts = re.split(marker_pattern, text, flags=re.IGNORECASE)
    
    combined_parts = []
    if len(parts) > 1:
        # Re-align markers with their corresponding text
        start_idx = 1 if not parts[0].strip() else 0
        for i in range(start_idx, len(parts), 2):
            if i + 1 < len(parts):
                combined_parts.append(f"{parts[i].strip()} {parts[i+1].strip()}")
            else:
                combined_parts.append(parts[i].strip())
        return combined_parts
    
    return [text]

def clean_and_parse(address_part):
    """
    Expands the address and prints the parsed components for verification.
    """
    if not address_part:
        return ""
    
    # 1. Expand: Standardizes "Rd" to "road", "St" to "street", etc.
    expansions = expand_address(address_part)
    standardized = expansions[0] if expansions else address_part
    
    # 2. Parse: Breaks down into {category: value}
    # We use the standardized version for better parsing accuracy
    parsed_components = parse_address(standardized)
    
    # Optional: You can format the parsed data into a string if you want to store it
    # For now, we return the standardized string as requested
    return standardized

def fix_digit_gaps(text: str) -> str:
    """
    Finds digits separated by a single space (e.g., '1 4' or '1 0 5') 
    and removes the space to unify the number.
    """
    # This regex uses positive lookahead/lookbehind to find spaces 
    # that are strictly between two digits.
    return re.sub(r'(?<=\d)\s+(?=\d)', '', text)

def transform_row(raw_content):
    """
    Checks for markers, splits if necessary, and processes each part.
    """
    # Trigger split if 'a)' or '1 a)' is found (case-insensitive)
    if re.search(r'\b\d?\s*a\)', raw_content, re.IGNORECASE):
        parts = split_english_markers(raw_content)
        cleaned_parts = [clean_and_parse(p) for p in parts]
        return " | ".join(cleaned_parts)
    else:
        return clean_and_parse(raw_content)

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found.")
        return

    print(f"Initializing Libpostal and reading {INPUT_FILE}...")
    
    with open(INPUT_FILE, mode='r', encoding='utf-8') as f_in:
        reader = csv.DictReader(f_in)
        fieldnames = reader.fieldnames
        rows = list(reader)

    processed_rows = []
    
    for row in rows:
        row['content'] = fix_digit_gaps(row['content'])  # Fix digit gaps before processing
        updated_text = transform_row(row['content'])
        new_row = dict(row)
        new_row['content'] = updated_text
        processed_rows.append(new_row)

    with open(OUTPUT_FILE, mode='w', encoding='utf-8', newline='') as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(processed_rows)

    print(f"✓ Processed {len(processed_rows)} rows.")
    print(f"✓ File saved as: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()