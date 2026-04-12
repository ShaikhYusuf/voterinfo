import pandas as pd
import re
import csv

FILENAME = "chinchpokli.mar.csv"
# Fix column names
# Read CSV
df = pd.read_csv(FILENAME)

# Clean column names
df.columns = df.columns.str.strip()

# Ensure Content column exists
if "Content" not in df.columns:
    df["Content"] = df.iloc[:, 2]

def extract_text(text):
    if pd.isna(text):
        return ""
    
    text = str(text)
    match = re.search(r"म्यु[\. ]घ[\. ]नं.*", text)
    return match.group(0).strip() if match else ""

# Apply extraction
df["MumNo"] = df["Content"].apply(extract_text)

# Write CSV with all fields in double quotes
df.to_csv(
    f"updated_{FILENAME}.csv",
    index=False,
    quoting=csv.QUOTE_ALL,
    encoding="utf-8-sig"
)

print("Done ✅")