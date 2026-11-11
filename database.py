"""
Database Operations and Schema Management for Snapit (TG-Manager).
"""
import sqlite3
from contextlib import contextmanager
from typing import List, Dict, Any, Optional

from config import DB_PATH, PAGE_SIZE, DEFAULT_CATEGORIES


@contextmanager
def connect_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 30000")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def ensure_schema():
    """Ensure database tables, indexes, and migrations are applied cleanly."""
    with connect_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS channels (
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
                last_checked TEXT,
                newly_added INTEGER NOT NULL DEFAULT 0
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                category_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS channel_categories (
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

        db.execute("""
            CREATE TABLE IF NOT EXISTS app_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # Migration: ensure newly_added column exists if upgraded from older schema
        columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(channels)").fetchall()
        }
        if "newly_added" not in columns:
            db.execute(
                "ALTER TABLE channels ADD COLUMN newly_added INTEGER NOT NULL DEFAULT 0"
            )

        db.execute("CREATE INDEX IF NOT EXISTS idx_channels_title ON channels(title COLLATE NOCASE)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_channels_username ON channels(username)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_channels_newly_added ON channels(newly_added)")

        # Seed initial categories if none exist
        cat_count = db.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
        if cat_count == 0:
            for cat_name in DEFAULT_CATEGORIES:
                db.execute(
                    "INSERT OR IGNORE INTO categories (name) VALUES (?)",
                    (cat_name,)
                )

        db.execute("""
            INSERT INTO app_metadata(key, value)
            VALUES ('sync_schema_version', '1')
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """)


def get_total_channel_count() -> int:
    with connect_db() as db:
        return db.execute("SELECT COUNT(*) FROM channels").fetchone()[0]


def get_newly_added_count() -> int:
    with connect_db() as db:
        return db.execute("SELECT COUNT(*) FROM channels WHERE newly_added = 1").fetchone()[0]


def get_uncategorised_count() -> int:
    with connect_db() as db:
        return db.execute("""
            SELECT COUNT(*)
            FROM channels ch
            WHERE ch.newly_added = 0
              AND NOT EXISTS (
                  SELECT 1 FROM channel_categories cc
                  WHERE cc.channel_id = ch.id
              )
        """).fetchone()[0]


def get_system_channel_count(kind: str) -> int:
    if kind == "newly":
        return get_newly_added_count()
    return get_uncategorised_count()


def get_system_channels(kind: str, page: int) -> List[sqlite3.Row]:
    offset = page * PAGE_SIZE
    if kind == "newly":
        where = "ch.newly_added = 1"
    else:
        where = """ch.newly_added = 0 AND NOT EXISTS (
            SELECT 1 FROM channel_categories cc
            WHERE cc.channel_id = ch.id
        )"""
    with connect_db() as db:
        return db.execute(f"""
            SELECT ch.id, ch.title, ch.username
            FROM channels ch
            WHERE {where}
            ORDER BY ch.title COLLATE NOCASE
            LIMIT ? OFFSET ?
        """, (PAGE_SIZE, offset)).fetchall()


def get_categories() -> List[sqlite3.Row]:
    with connect_db() as db:
        return db.execute("SELECT category_id, name FROM categories ORDER BY category_id").fetchall()


def get_category(category_id: int) -> Optional[sqlite3.Row]:
    with connect_db() as db:
        return db.execute("SELECT * FROM categories WHERE category_id = ?", (category_id,)).fetchone()


def get_channel(channel_id: str) -> Optional[sqlite3.Row]:
    with connect_db() as db:
        return db.execute("SELECT * FROM channels WHERE id = ?", (str(channel_id),)).fetchone()


def get_channel_count(category_id: int) -> int:
    with connect_db() as db:
        return db.execute(
            "SELECT COUNT(*) FROM channel_categories WHERE category_id = ?",
            (category_id,)
        ).fetchone()[0]


def get_category_channels(category_id: int, page: int) -> List[sqlite3.Row]:
    offset = page * PAGE_SIZE
    with connect_db() as db:
        return db.execute("""
            SELECT ch.id, ch.title, ch.username
            FROM channels ch
            JOIN channel_categories cc ON cc.channel_id = ch.id
            WHERE cc.category_id = ?
            ORDER BY ch.title COLLATE NOCASE
            LIMIT ? OFFSET ?
        """, (category_id, PAGE_SIZE, offset)).fetchall()


def search_channels(term: str) -> List[sqlite3.Row]:
    with connect_db() as db:
        return db.execute("""
            SELECT id, title, username
            FROM channels
            WHERE title LIKE ? OR username LIKE ?
            ORDER BY title COLLATE NOCASE
            LIMIT 15
        """, (f"%{term}%", f"%{term}%")).fetchall()


def get_channel_categories(channel_id: str) -> List[sqlite3.Row]:
    with connect_db() as db:
        return db.execute("""
            SELECT c.category_id, c.name
            FROM categories c
            JOIN channel_categories cc
              ON cc.category_id = c.category_id
            WHERE cc.channel_id = ?
            ORDER BY c.category_id
        """, (str(channel_id),)).fetchall()


def create_category(name: str):
    with connect_db() as db:
        db.execute("INSERT INTO categories (name, created_at) VALUES (?, datetime('now'))", (name,))


def rename_category(category_id: int, name: str):
    with connect_db() as db:
        db.execute("UPDATE categories SET name = ? WHERE category_id = ?", (name, category_id))


def delete_category(category_id: int):
    with connect_db() as db:
        db.execute("DELETE FROM categories WHERE category_id = ?", (category_id,))


def toggle_channel_category(channel_id: str, category_id: int):
    with connect_db() as db:
        exists = db.execute("""
            SELECT 1 FROM channel_categories
            WHERE channel_id = ? AND category_id = ?
        """, (str(channel_id), category_id)).fetchone()

        if exists:
            db.execute("""
                DELETE FROM channel_categories
                WHERE channel_id = ? AND category_id = ?
            """, (str(channel_id), category_id))
        else:
            db.execute("""
                INSERT INTO channel_categories
                    (channel_id, category_id, assigned_at)
                VALUES (?, ?, datetime('now'))
            """, (str(channel_id), category_id))
            # Once classified, mark newly_added as 0
            db.execute("UPDATE channels SET newly_added = 0 WHERE id = ?", (str(channel_id),))


def save_sync_results(discovered: List[Dict[str, Any]], now: str) -> Dict[str, int]:
    """Persist discovered chat-list dialogs and reconcile removals safely."""
    added = 0
    updated = 0
    removed = 0

    with connect_db() as db:
        for item in discovered:
            exists = db.execute("SELECT 1 FROM channels WHERE id = ?", (item["id"],)).fetchone()
            if exists:
                db.execute("""
                    UPDATE channels
                    SET title = ?,
                        username = ?,
                        type = ?,
                        account_visibility = 'Found in main chat list',
                        membership_status = 'Present in main chat list',
                        last_checked = ?
                    WHERE id = ?
                """, (item["title"], item["username"], item["type"], now, item["id"]))
                updated += 1
            else:
                db.execute("""
                    INSERT INTO channels (
                        title, username, id, type, account_visibility,
                        channel_status, membership_status, access_model,
                        content_availability, invite_link, payment_notes,
                        verification_notes, last_checked, newly_added
                    ) VALUES (?, ?, ?, ?, 'Found in main chat list',
                              'Unknown', 'Present in main chat list',
                              'Unknown', 'Unknown', '', '', '', ?, 1)
                """, (item["title"], item["username"], item["id"], item["type"], now))
                added += 1

        if discovered:
            seen_ids = [item["id"] for item in discovered]
            db.execute("CREATE TEMP TABLE IF NOT EXISTS temp_seen_dialogs (id TEXT PRIMARY KEY)")
            db.execute("DELETE FROM temp_seen_dialogs")
            db.executemany(
                "INSERT OR IGNORE INTO temp_seen_dialogs (id) VALUES (?)",
                [(item_id,) for item_id in seen_ids]
            )
            cursor = db.execute("""
                DELETE FROM channels
                WHERE membership_status = 'Present in main chat list'
                  AND id NOT IN (SELECT id FROM temp_seen_dialogs)
            """)
            removed = cursor.rowcount
            db.execute("DROP TABLE IF EXISTS temp_seen_dialogs")

        db.execute("""
            INSERT INTO app_metadata(key, value)
            VALUES ('last_sync_at', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (now,))
        db.execute("""
            INSERT INTO app_metadata(key, value)
            VALUES ('last_sync_seen_count', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (str(len(discovered)),))

    return {
        "seen": len(discovered),
        "added": added,
        "updated": updated,
        "removed": removed,
        "newly_added": get_newly_added_count(),
    }
