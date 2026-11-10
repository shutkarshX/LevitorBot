import sqlite3

db = sqlite3.connect("data/tg_manager.db")

print("DATABASE TABLES:")
for (table,) in db.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
):
    print(f"\n{table}")
    for col in db.execute(f"PRAGMA table_info({table})"):
        print(" ", col[1], col[2])

print("\nCHANNEL COUNT:",
      db.execute("SELECT COUNT(*) FROM channels").fetchone()[0])

print("CATEGORY COUNT:",
      db.execute("SELECT COUNT(*) FROM categories").fetchone()[0])

db.close()
