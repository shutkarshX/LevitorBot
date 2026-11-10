import sqlite3

db = sqlite3.connect("data/tg_manager.db")
db.row_factory = sqlite3.Row

print("=== CATEGORY COUNTS ===")
for r in db.execute("""
    SELECT c.name, COUNT(cc.channel_id) AS total
    FROM categories c
    LEFT JOIN channel_categories cc ON c.category_id = cc.category_id
    GROUP BY c.category_id
    ORDER BY c.category_id
"""):
    print(f"{r['name']}: {r['total']}")

print("\n=== DESTINATION READINESS ===")
print("Total channels:", db.execute("SELECT COUNT(*) FROM channels").fetchone()[0])
print("With username:", db.execute("SELECT COUNT(*) FROM channels WHERE TRIM(COALESCE(username,'')) != ''").fetchone()[0])
print("With invite link:", db.execute("SELECT COUNT(*) FROM channels WHERE TRIM(COALESCE(invite_link,'')) != ''").fetchone()[0])
print("Without either:", db.execute("""
    SELECT COUNT(*) FROM channels
    WHERE TRIM(COALESCE(username,'')) = ''
    AND TRIM(COALESCE(invite_link,'')) = ''
""").fetchone()[0])

for field in ["type", "account_visibility", "channel_status",
              "membership_status", "access_model", "content_availability"]:
    print(f"\n=== {field.upper()} ===")
    for r in db.execute(f"""
        SELECT COALESCE(NULLIF(TRIM({field}),''), '[empty]') AS value,
               COUNT(*) AS total
        FROM channels GROUP BY value ORDER BY total DESC
    """):
        print(f"{r['value']}: {r['total']}")

db.close()
