import sqlite3
from pathlib import Path

path = Path("tg_manager_readonly.session")

if not path.exists():
    raise SystemExit("Session file not found.")

db = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)

tables = [
    row[0] for row in
    db.execute("SELECT name FROM sqlite_master WHERE type='table'")
]

print("Session tables:", ", ".join(tables))

if "entities" in tables:
    columns = [
        row[1] for row in db.execute("PRAGMA table_info(entities)")
    ]
    print("Entity columns:", ", ".join(columns))

    total = db.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    named = db.execute("""
        SELECT COUNT(*) FROM entities
        WHERE username IS NOT NULL AND TRIM(username) != ''
    """).fetchone()[0]

    print("Cached entities:", total)
    print("Cached public usernames:", named)

db.close()
