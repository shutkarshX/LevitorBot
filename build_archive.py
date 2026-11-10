
import csv
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent

SOURCE = BASE_DIR / "channel_inventory.csv"
ARCHIVE = BASE_DIR / "channel_archive.csv"

EXTRA_FIELDS = [
    "account_visibility",
    "channel_status",
    "membership_status",
    "access_model",
    "content_availability",
    "invite_link",
    "payment_notes",
    "verification_notes",
    "last_checked",
]

DEFAULTS = {
    "account_visibility": "Found in account dialogs",
    "channel_status": "Unknown",
    "membership_status": "Unknown",
    "access_model": "Unknown",
    "content_availability": "Unknown",
    "invite_link": "",
    "payment_notes": "",
    "verification_notes": "",
    "last_checked": "",
}

def read_csv(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def main():
    if not SOURCE.exists():
        raise FileNotFoundError(
            f"Original inventory not found: {SOURCE}"
        )

    source_rows = read_csv(SOURCE)

    # Preserve previous classifications when rebuilding.
    existing = {}

    if ARCHIVE.exists():
        for row in read_csv(ARCHIVE):
            existing[row.get("id", "")] = row

    output_rows = []

    for original in source_rows:
        channel_id = original.get("id", "")
        previous = existing.get(channel_id, {})

        record = dict(original)

        for field in EXTRA_FIELDS:
            old_value = previous.get(field, "")
            record[field] = (
                old_value if old_value != ""
                else DEFAULTS[field]
            )

        output_rows.append(record)

    fieldnames = list(source_rows[0].keys()) + EXTRA_FIELDS

    with open(
        ARCHIVE,
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(output_rows)

    print("=" * 50)
    print("       TG MANAGER - ARCHIVE BUILDER")
    print("=" * 50)
    print(f"Original records : {len(source_rows)}")
    print(f"Archived records : {len(output_rows)}")
    print(f"Preserved records: {len(existing)}")
    print(f"\nCreated:\n{ARCHIVE}")
    print("\nAll unverified classifications remain Unknown.")
    print("No Telegram account changes were made.")

if __name__ == "__main__":
    main()
