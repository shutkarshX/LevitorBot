import csv
import sqlite3
import shutil
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
BACKUP_ROOT = ROOT / "backups"
DATA_DIR = ROOT / "data"

ARCHIVE = ROOT / "channel_archive.csv"
INVENTORY = ROOT / "channel_inventory.csv"
DB = (DATA_DIR / "levitor.db") if (DATA_DIR / "levitor.db").exists() else (DATA_DIR / "tg_manager.db")

CATEGORIES = [
    "Direct Content",
    "Link Sharing",
    "Join Required",
    "Paid",
    "Redirect",
    "Ad to Watch",
    "Empty / No Content",
    "Garbage",
    "Old Content",
]

EXPECTED_COLUMNS = [
    "title",
    "username",
    "id",
    "type",
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

def read_csv(path, expected_columns):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != expected_columns:
            raise ValueError(
                f"Unexpected CSV schema in {path.name}: {reader.fieldnames}"
            )
        rows = list(reader)

    return rows

def main():
    print("=" * 55)
    print("TG MANAGER — SAFE DATABASE MIGRATION")
    print("=" * 55)

    if not ARCHIVE.is_file():
        raise FileNotFoundError(ARCHIVE)

    if not INVENTORY.is_file():
        raise FileNotFoundError(INVENTORY)

    if DB.exists():
        raise FileExistsError(
            f"Database already exists: {DB}\n"
            "Nothing was overwritten. Inspect it before proceeding."
        )

    archive_rows = read_csv(ARCHIVE, EXPECTED_COLUMNS)
    inventory_rows = read_csv(INVENTORY, ["title", "username", "id", "type"])

    if not archive_rows:
        raise ValueError("Archive is empty.")

    archive_ids = [row["id"].strip() for row in archive_rows]
    inventory_ids = [row["id"].strip() for row in inventory_rows]

    if any(not x.isdigit() for x in archive_ids):
        raise ValueError("Archive contains an empty or non-numeric ID.")

    if len(set(archive_ids)) != len(archive_ids):
        raise ValueError("Duplicate archive IDs detected.")

    if len(set(inventory_ids)) != len(inventory_ids):
        raise ValueError("Duplicate inventory IDs detected.")

    if set(archive_ids) != set(inventory_ids):
        raise ValueError("Archive and inventory IDs do not match.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BACKUP_ROOT / f"pre_migration_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)

    print("\n1. Creating backups...")

    files_to_backup = [
        ARCHIVE,
        INVENTORY,
        ROOT / "build_archive.py",
        ROOT / "dashboard.py",
        ROOT / "inspect_telegram.py",
    ]

    manifest = []

    for source in files_to_backup:
        if source.is_file():
            destination = backup_dir / source.name
            shutil.copy2(source, destination)
            manifest.append(source.name)
            print(f"  Backed up: {source.name}")

    (backup_dir / "backup_manifest.txt").write_text(
        "\n".join(manifest) + "\n",
        encoding="utf-8"
    )

    print("\n2. Creating SQLite database...")

    connection = sqlite3.connect(DB)

    try:
        connection.execute("PRAGMA foreign_keys = ON")

        connection.execute("""
            CREATE TABLE channels (
                title TEXT NOT NULL,
                username TEXT,
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                account_visibility TEXT NOT NULL,
                channel_status TEXT NOT NULL,
                membership_status TEXT NOT NULL,
                access_model TEXT NOT NULL,
                content_availability TEXT NOT NULL,
                invite_link TEXT,
                payment_notes TEXT,
                verification_notes TEXT,
                last_checked TEXT
            )
        """)

        connection.execute("""
            CREATE TABLE categories (
                category_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        connection.execute("""
            CREATE TABLE channel_categories (
                channel_id TEXT NOT NULL,
                category_id INTEGER NOT NULL,
                assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (channel_id, category_id),
                FOREIGN KEY (channel_id)
                    REFERENCES channels(id) ON DELETE CASCADE,
                FOREIGN KEY (category_id)
                    REFERENCES categories(category_id) ON DELETE CASCADE
            )
        """)

        connection.execute("""
            CREATE TABLE app_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        connection.execute("""
            CREATE INDEX idx_channels_title
            ON channels(title COLLATE NOCASE)
        """)

        connection.execute("""
            CREATE INDEX idx_channels_username
            ON channels(username)
        """)

        print("\n3. Importing channel records...")

        placeholders = ", ".join("?" for _ in EXPECTED_COLUMNS)
        column_names = ", ".join(EXPECTED_COLUMNS)

        insert_sql = (
            f"INSERT INTO channels ({column_names}) "
            f"VALUES ({placeholders})"
        )

        connection.executemany(
            insert_sql,
            [
                tuple(row[column] for column in EXPECTED_COLUMNS)
                for row in archive_rows
            ]
        )

        print("  Imported:", len(archive_rows))

        print("\n4. Creating initial categories...")

        connection.executemany(
            "INSERT INTO categories (name) VALUES (?)",
            [(name,) for name in CATEGORIES]
        )

        connection.executemany(
            "INSERT INTO app_metadata (key, value) VALUES (?, ?)",
            [
                ("schema_version", "1"),
                ("migration_source", "channel_archive.csv"),
                ("migration_timestamp", timestamp),
                ("initial_channel_count", str(len(archive_rows))),
            ]
        )

        connection.commit()

        print("\n5. Verifying database...")

        channel_count = connection.execute(
            "SELECT COUNT(*) FROM channels"
        ).fetchone()[0]

        unique_ids = connection.execute(
            "SELECT COUNT(DISTINCT id) FROM channels"
        ).fetchone()[0]

        category_count = connection.execute(
            "SELECT COUNT(*) FROM categories"
        ).fetchone()[0]

        assignment_count = connection.execute(
            "SELECT COUNT(*) FROM channel_categories"
        ).fetchone()[0]

        integrity = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        foreign_keys = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        if channel_count != len(archive_rows):
            raise RuntimeError("Imported record count mismatch.")

        if unique_ids != len(archive_rows):
            raise RuntimeError("Unique ID verification failed.")

        if category_count != len(CATEGORIES):
            raise RuntimeError("Category count mismatch.")

        if assignment_count != 0:
            raise RuntimeError("Unexpected category assignments.")

        if integrity != "ok":
            raise RuntimeError(f"SQLite integrity error: {integrity}")

        if foreign_keys:
            raise RuntimeError("Foreign key verification failed.")

        print("\n" + "=" * 55)
        print("MIGRATION SUCCESSFUL")
        print("=" * 55)
        print("Channels:", channel_count)
        print("Unique IDs:", unique_ids)
        print("Categories:", category_count)
        print("Category assignments:", assignment_count)
        print("SQLite integrity:", integrity)
        print("Foreign key errors:", len(foreign_keys))
        print("Database:", DB)
        print("Backup:", backup_dir)
        print("\nOriginal CSV files were not modified.")

    except Exception:
        connection.rollback()
        connection.close()

        if DB.exists():
            DB.unlink()

        raise

    finally:
        if connection:
            try:
                connection.close()
            except Exception:
                pass

if __name__ == "__main__":
    main()
