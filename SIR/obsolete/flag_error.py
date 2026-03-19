"""
Voter CSV OCR Error Flagger
============================
Reads the extracted voter CSV and flags rows that likely contain
OCR errors — English letters mixed into Marathi text fields.

Usage:
    python flag_ocr_errors.py voters.csv

Output:
    - voters_flagged.csv  : original data + a new 'needs_review' column
    - voters_errors.csv   : only the flagged rows, for quick manual fixing
"""

import re
import sys
import csv

# ── Patterns that suggest OCR noise in a Marathi text field ──
NOISE_PATTERNS = [
    r'\b[A-Z]{2,}\b',          # ALL-CAPS English words: ACA, IRS, MT (but not voter IDs)
    r'\b[a-z]{1,3}\b',         # short lowercase English: q, a, ay, sय
    r'fesse|Tost|TPIS|Bisa',   # known bad OCR fragments
    r'\d+[A-Za-z]+\d*',        # digits mixed with letters in names
]

NOISE_RE = re.compile('|'.join(NOISE_PATTERNS))

# Fields to check for OCR noise (not voter_id which legitimately has letters)
TEXT_FIELDS = [
    'मतदाराचे नाव (Voter Name)',
    'नाते (Relation)',
    'नातेवाईकाचे नाव (Relative Name)',
    'लिंग (Gender)',
]

# Also flag sr_no that looks merged (e.g. "4457" when max voters ~1500)
def is_merged_sr_no(sr):
    try:
        return int(sr) > 1500
    except ValueError:
        return False


def flag_row(row):
    """Return a string describing what looks wrong, or '' if row is clean."""
    issues = []

    # Check serial number
    sr = row.get('अ.क्र. (Sr No)', '')
    if is_merged_sr_no(sr):
        issues.append(f"Sr No looks merged: {sr}")

    # Check text fields for OCR noise
    for field in TEXT_FIELDS:
        val = row.get(field, '')
        if val and NOISE_RE.search(val):
            # Exclude legitimate Marathi characters around the match
            match = NOISE_RE.search(val)
            issues.append(f"{field}: '{match.group()}' in '{val}'")

    return ' | '.join(issues)


def main():
    if len(sys.argv) < 2:
        print("Usage: python flag_ocr_errors.py voters.csv")
        sys.exit(1)

    input_path  = sys.argv[1]
    flagged_path = input_path.replace('.csv', '_flagged.csv')
    errors_path  = input_path.replace('.csv', '_errors_only.csv')

    all_rows     = []
    flagged_rows = []

    with open(input_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames + ['needs_review', 'issue_detail']

        for row in reader:
            issue = flag_row(row)
            row['needs_review'] = 'YES' if issue else ''
            row['issue_detail'] = issue
            all_rows.append(row)
            if issue:
                flagged_rows.append(row)

    # Write full file with flags
    with open(flagged_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    # Write errors-only file
    with open(errors_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flagged_rows)

    total   = len(all_rows)
    flagged = len(flagged_rows)
    print(f"\n✅ Done!")
    print(f"   Total rows    : {total}")
    print(f"   Flagged rows  : {flagged} ({100*flagged//total}%)")
    print(f"   Clean rows    : {total - flagged}")
    print(f"\n📄 Full file with flags : {flagged_path}")
    print(f"📄 Errors only          : {errors_path}")
    print(f"\nOpen {errors_path} in Excel to manually fix the flagged rows,")
    print(f"then copy corrections back into {flagged_path}.\n")


if __name__ == "__main__":
    main()