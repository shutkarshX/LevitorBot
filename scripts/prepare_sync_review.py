import sqlite3
from pathlib import Path

root = Path(".")
output = root / "data" / "implementation_review.txt"

parts = []
parts.append("TG MANAGER PRE-SYNC IMPLEMENTATION REVIEW\n")

parts.append("\n=== CURRENT BOT SOURCE ===\n")
parts.append((root / "tg_manager_bot.py").read_text(encoding="utf-8"))

db = sqlite3.connect("data/tg_manager.db")

parts.append("\n\n=== DATABASE SCHEMA ===\n")
for row in db.execute("""
    SELECT sql FROM sqlite_master
    WHERE sql IS NOT NULL
    ORDER BY type, name
"""):
    parts.append(str(row[0]) + ";\n")

parts.append("\n=== DATABASE COUNTS ===\n")
for table in ["channels", "categories", "channel_categories", "app_metadata"]:
    count = db.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
    parts.append(f"{table}: {count}\n")

parts.append("\n=== CATEGORY ASSIGNMENTS ===\n")
for row in db.execute("""
    SELECT c.name, COUNT(cc.channel_id)
    FROM categories c
    LEFT JOIN channel_categories cc ON cc.category_id = c.category_id
    GROUP BY c.category_id ORDER BY c.category_id
"""):
    parts.append(f"{row[0]}: {row[1]}\n")

db.close()

parts.append("\n=== GITIGNORE ===\n")
gitignore = root / ".gitignore"
if gitignore.exists():
    parts.append(gitignore.read_text(encoding="utf-8"))

output.write_text("".join(parts), encoding="utf-8")
print("Review report created:", output.resolve())
