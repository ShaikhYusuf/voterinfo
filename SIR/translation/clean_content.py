import csv
import re

INPUT_FILE = "updated.chinchpokli.mar.csv"
OUTPUT_FILE = "updated.chinchpokli.mar.cleaned.csv"

with open(INPUT_FILE, "r", encoding="utf-8") as f_in, \
     open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f_out:

    lines = csv.reader(f_in)
    writer = csv.writer(f_out)

    header_line = next(lines)

    CONTENT_INDEX = -1
    for i, h in enumerate(header_line):
        if h.strip().lower() == "content":
            CONTENT_INDEX = i

    if CONTENT_INDEX == -1:
        raise Exception("Content column not found")

    writer.writerow(header_line)

    last_content = None
    for line in lines:
        if not line:
            continue

        if len(line) <= CONTENT_INDEX:
            continue

        # Get content from the content column
        fixed_content = line[CONTENT_INDEX]

        # Clean content
        fixed_content = re.sub(r'^\s*\d{1,2}\s*', '', fixed_content)
        fixed_content = re.sub(r'^\s*.*#', '', fixed_content)
        fixed_content = fixed_content.replace(",", ".")
        fixed_content = fixed_content.strip().strip('"')

        if fixed_content == last_content:
            continue

        # Rebuild row: keep all columns, only modify content column
        new_row = line[:CONTENT_INDEX] + [fixed_content] + line[CONTENT_INDEX+1:]
        writer.writerow(new_row)
        last_content = fixed_content