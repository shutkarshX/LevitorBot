import os
import sqlite3
import logging
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import PeerChannel, PeerChat
from telethon.tl import types

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# --------------------------------------------------
# Configuration
# --------------------------------------------------

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "data" / "tg_manager.db"
SESSION_PATH = str(BASE / "tg_manager_readonly")

load_dotenv(BASE / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = os.getenv("TG_API_ID")
API_HASH = os.getenv("TG_API_HASH")

if not BOT_TOKEN or not API_ID or not API_HASH:
    raise RuntimeError("Required environment configuration is missing.")

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)

PAGE_SIZE = 8

# Main Telegram chat-list sync only. Archived dialogs (folder 1), DMs,
# and bot conversations are deliberately excluded.


# --------------------------------------------------
# Database
# --------------------------------------------------

def connect_db():
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 30000")
    return db


def ensure_schema():
    """Add sync metadata without rebuilding or replacing existing records."""
    with connect_db() as db:
        columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(channels)").fetchall()
        }
        if "newly_added" not in columns:
            db.execute(
                "ALTER TABLE channels ADD COLUMN newly_added "
                "INTEGER NOT NULL DEFAULT 0"
            )
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_channels_newly_added
            ON channels(newly_added)
        """)
        db.execute("""
            INSERT INTO app_metadata(key, value)
            VALUES ('sync_schema_version', '1')
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """)


def get_total_channel_count():
    with connect_db() as db:
        return db.execute("SELECT COUNT(*) FROM channels").fetchone()[0]


def get_newly_added_count():
    with connect_db() as db:
        return db.execute(
            "SELECT COUNT(*) FROM channels WHERE newly_added = 1"
        ).fetchone()[0]


def get_uncategorised_count():
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


def get_system_channels(kind, page):
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


def get_system_channel_count(kind):
    if kind == "newly":
        return get_newly_added_count()
    return get_uncategorised_count()


async def sync_main_dialogs(application):
    """Import only channels/groups in the main chat list; never DMs or bots."""
    client = application.bot_data["tg_client"]
    now = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).isoformat(timespec="seconds")
    discovered = []
    # Telethon folder=0 means the main chat list; archived folder=1 is excluded.
    async for dialog in client.iter_dialogs(folder=0):
        entity = dialog.entity

        if isinstance(entity, types.Channel):
            kind = "Broadcast Channel" if getattr(entity, "broadcast", False) else "Supergroup"
        elif isinstance(entity, types.Chat):
            kind = "Basic Group"
        else:
            # Excludes one-to-one users, bots, and non-group dialog types.
            continue

        discovered.append({
            "id": str(entity.id),
            "title": (getattr(entity, "title", None) or "Untitled").strip(),
            "username": (getattr(entity, "username", None) or "").strip(),
            "type": kind,
        })

    added = 0
    updated = 0
    with connect_db() as db:
        for item in discovered:
            exists = db.execute(
                "SELECT 1 FROM channels WHERE id = ?", (item["id"],)
            ).fetchone()
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
                """, (
                    item["title"], item["username"], item["type"],
                    now, item["id"]
                ))
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
                """, (
                    item["title"], item["username"], item["id"],
                    item["type"], now
                ))
                added += 1

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
        "newly_added": get_newly_added_count(),
    }


def get_categories():
    with connect_db() as db:
        return db.execute(
            "SELECT category_id, name FROM categories ORDER BY category_id"
        ).fetchall()


def get_channel(channel_id):
    with connect_db() as db:
        return db.execute(
            "SELECT * FROM channels WHERE id = ?",
            (str(channel_id),)
        ).fetchone()


def get_channel_count(category_id):
    with connect_db() as db:
        return db.execute(
            "SELECT COUNT(*) FROM channel_categories WHERE category_id = ?",
            (category_id,)
        ).fetchone()[0]


def get_category_channels(category_id, page):
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


def search_channels(term):
    with connect_db() as db:
        return db.execute("""
            SELECT id, title, username
            FROM channels
            WHERE title LIKE ? OR username LIKE ?
            ORDER BY title COLLATE NOCASE
            LIMIT 15
        """, (f"%{term}%", f"%{term}%")).fetchall()


def get_channel_categories(channel_id):
    with connect_db() as db:
        return db.execute("""
            SELECT c.category_id, c.name
            FROM categories c
            JOIN channel_categories cc
              ON cc.category_id = c.category_id
            WHERE cc.channel_id = ?
            ORDER BY c.category_id
        """, (str(channel_id),)).fetchall()


# --------------------------------------------------
# Admin security
# --------------------------------------------------

def is_admin(update, context):
    user = update.effective_user
    chat = update.effective_chat

    return (
        user is not None
        and chat is not None
        and chat.type == "private"
        and user.id == context.application.bot_data.get("admin_id")
    )


async def deny(update):
    if update.callback_query:
        await update.callback_query.answer(
            "This bot is private.", show_alert=True
        )
    elif update.effective_message:
        await update.effective_message.reply_text(
            "This bot is private."
        )


async def show(update, text, keyboard=None):
    markup = InlineKeyboardMarkup(keyboard) if keyboard else None

    if update.callback_query:
        await update.callback_query.message.edit_text(
            text, reply_markup=markup
        )
    else:
        await update.effective_message.reply_text(
            text, reply_markup=markup
        )


# --------------------------------------------------
# Main menu
# --------------------------------------------------

def home_keyboard():
    return [
        [InlineKeyboardButton("Browse categories", callback_data="cats")],
        [InlineKeyboardButton(
            f"Newly Added ({get_newly_added_count()})",
            callback_data="newly:0"
        )],
        [InlineKeyboardButton(
            f"Uncategorised ({get_uncategorised_count()})",
            callback_data="uncat:0"
        )],
        [InlineKeyboardButton("Sync main chat list", callback_data="sync")],
        [InlineKeyboardButton("Search channels", callback_data="search")],
        [InlineKeyboardButton("Create category", callback_data="newcat")],
        [InlineKeyboardButton("Download database backup", callback_data="backup")],
    ]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context):
        await deny(update)
        return

    context.user_data.clear()

    await show(
        update,
        f"TG Manager\n\nYour Telegram channel library.\n\n"
        f"{get_total_channel_count()} destinations · "
        f"{len(get_categories())} categories · "
        f"{get_newly_added_count()} newly added",
        home_keyboard(),
    )


async def categories(update, context):
    rows = get_categories()
    keyboard = []

    for row in rows:
        count = get_channel_count(row["category_id"])
        keyboard.append([
            InlineKeyboardButton(
                f"{row['name']} ({count})",
                callback_data=f"cat:{row['category_id']}:0",
            )
        ])

    keyboard.append([
        InlineKeyboardButton("Search", callback_data="search"),
        InlineKeyboardButton("Home", callback_data="home"),
    ])

    await show(update, "Your categories\n\nSelect a category:", keyboard)


async def system_category_page(update, context, kind, page):
    total = get_system_channel_count(kind)
    channels = get_system_channels(kind, page)
    title = "Newly Added" if kind == "newly" else "Uncategorised"
    keyboard = []

    for channel in channels:
        keyboard.append([InlineKeyboardButton(
            channel["title"][:55],
            callback_data=f"ch:{channel['id']}:0:{page}"
        )])

    navigation = []
    if page > 0:
        navigation.append(InlineKeyboardButton(
            "Previous", callback_data=f"{kind}:{page - 1}"
        ))
    if (page + 1) * PAGE_SIZE < total:
        navigation.append(InlineKeyboardButton(
            "Next", callback_data=f"{kind}:{page + 1}"
        ))
    if navigation:
        keyboard.append(navigation)

    keyboard.append([InlineKeyboardButton("Home", callback_data="home")])
    message = (
        f"{title}\n{total} destination(s)\n\n"
        + ("Select a destination:" if channels else "Nothing here right now.")
    )
    await show(update, message, keyboard)


async def run_sync(update, context):
    query = update.callback_query
    await query.edit_message_text(
        "Syncing your main Telegram chat list…\n\n"
        "Personal DMs, bot chats, and archived conversations are excluded."
    )
    try:
        result = await sync_main_dialogs(context.application)
    except Exception:
        logging.exception("Main chat-list sync failed.")
        await query.message.reply_text(
            "Sync failed. Your existing records and category assignments "
            "were not intentionally removed. Check the bot log and try again."
        )
        return

    await query.message.reply_text(
        "Sync completed.\n\n"
        f"Main-list channels/groups checked: {result['seen']}\n"
        f"New destinations: {result['added']}\n"
        f"Existing destinations checked: {result['updated']}\n"
        f"Still in Newly Added: {result['newly_added']}",
        reply_markup=InlineKeyboardMarkup(home_keyboard())
    )



async def send_database_backup(update, context):
    """Create a consistent SQLite snapshot and send it privately to the admin."""
    if not is_admin(update, context):
        await deny(update)
        return

    message = update.effective_message
    if not DB_PATH.is_file():
        await message.reply_text("Backup failed: the database file was not found.")
        return

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")
    filename = f"tg_manager_backup_{timestamp}.db"

    try:
        # SQLite's online backup API safely snapshots a live database,
        # including committed changes in its WAL, without copying sidecars.
        with tempfile.TemporaryDirectory(prefix="tg_manager_backup_") as temp_dir:
            backup_path = Path(temp_dir) / filename

            with closing(sqlite3.connect(DB_PATH, timeout=30)) as source:
                with closing(sqlite3.connect(backup_path, timeout=30)) as destination:
                    source.backup(destination)
                    integrity = destination.execute(
                        "PRAGMA integrity_check"
                    ).fetchone()[0]

            if integrity != "ok":
                raise sqlite3.DatabaseError(
                    f"Backup integrity check failed: {integrity}"
                )

            size = backup_path.stat().st_size
            with backup_path.open("rb") as backup_file:
                await message.reply_document(
                    document=backup_file,
                    filename=filename,
                    caption=(
                        "TG Manager database backup\\n"
                        f"Created: {timestamp}\\n"
                        f"Size: {size:,} bytes\\n"
                        "Integrity check: OK"
                    ),
                )

        logging.info("Database backup sent to administrator (%s bytes).", size)

    except Exception:
        logging.exception("Could not create or send database backup.")
        await message.reply_text(
            "Database backup failed. Your live database was not intentionally "
            "modified. Check the hosting logs and try again."
        )


# --------------------------------------------------
# Category browsing
# --------------------------------------------------

async def category_page(update, context, category_id, page):
    with connect_db() as db:
        category = db.execute(
            "SELECT * FROM categories WHERE category_id = ?",
            (category_id,)
        ).fetchone()

    if not category:
        await show(update, "Category not found.", [
            [InlineKeyboardButton("Categories", callback_data="cats")]
        ])
        return

    total = get_channel_count(category_id)
    channels = get_category_channels(category_id, page)

    keyboard = []

    for channel in channels:
        keyboard.append([
            InlineKeyboardButton(
                channel["title"][:55],
                callback_data=f"ch:{channel['id']}:{category_id}:{page}",
            )
        ])

    navigation = []

    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                "Previous",
                callback_data=f"cat:{category_id}:{page - 1}",
            )
        )

    if (page + 1) * PAGE_SIZE < total:
        navigation.append(
            InlineKeyboardButton(
                "Next",
                callback_data=f"cat:{category_id}:{page + 1}",
            )
        )

    if navigation:
        keyboard.append(navigation)

    keyboard.extend([
        [InlineKeyboardButton("Rename category", callback_data=f"rename:{category_id}")],
        [InlineKeyboardButton("Delete category", callback_data=f"delete:{category_id}")],
        [InlineKeyboardButton("Back to categories", callback_data="cats")],
    ])

    text = (
        f"{category['name']}\n"
        f"{total} assigned channel(s)\n\n"
    )

    if channels:
        text += "Select a channel:"
    else:
        text += "No channels assigned yet.\nSearch for a channel to assign it."

    await show(update, text, keyboard)


# --------------------------------------------------
# Channel details and opening
# --------------------------------------------------

async def channel_page(update, context, channel_id, category_id=0, page=0):
    channel = get_channel(channel_id)

    if not channel:
        await show(update, "Channel not found.")
        return

    assigned = get_channel_categories(channel_id)

    text = (
        f"{channel['title']}\n\n"
        f"Type: {channel['type']}\n"
        f"Username: @{channel['username']}"
        if channel["username"]
        else f"{channel['title']}\n\nType: {channel['type']}\nNo public username"
    )

    text += "\n\nAssigned categories:\n"

    if assigned:
        text += "\n".join(f"• {row['name']}" for row in assigned)
    else:
        text += "None"

    keyboard = [
        [InlineKeyboardButton("Open in Telegram", callback_data=f"open:{channel_id}")]
    ]

    keyboard.append([
        InlineKeyboardButton(
            "Manage category assignments",
            callback_data=f"assign:{channel_id}:{category_id}:{page}",
        )
    ])

    if category_id:
        keyboard.append([
            InlineKeyboardButton(
                "Back to channel list",
                callback_data=f"cat:{category_id}:{page}",
            )
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("Back to search", callback_data="search")
        ])

    keyboard.append([
        InlineKeyboardButton("Home", callback_data="home")
    ])

    await show(update, text, keyboard)


async def open_channel(update, context, channel_id):
    channel = get_channel(channel_id)

    if not channel:
        await update.callback_query.answer(
            "Channel not found.", show_alert=True
        )
        return

    username = (channel["username"] or "").strip().lstrip("@")

    if username:
        url = f"https://t.me/{username}"
    elif channel["type"] == "Basic Group":
        # Telegram's /c/ message links are for channels and supergroups.
        # Do not manufacture a link that may not open a basic group.
        await update.callback_query.answer(
            "This is a basic group. Open it from your Telegram chat list.",
            show_alert=True,
        )
        return
    else:
        try:
            client = context.application.bot_data["tg_client"]
            peer = await client.get_input_entity(PeerChannel(int(channel_id)))
            messages = await client.get_messages(peer, limit=1)

            if not messages or not messages[0].id:
                await update.callback_query.answer(
                    "This destination has no available message link yet.",
                    show_alert=True,
                )
                return

            url = f"https://t.me/c/{channel_id}/{messages[0].id}"

        except Exception:
            logging.exception("Could not resolve private channel.")
            await update.callback_query.answer(
                "Could not generate an opening link. Check account access.",
                show_alert=True,
            )
            return

    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        f"Open {channel['title']}:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Open in Telegram", url=url)
        ]]),
    )


# --------------------------------------------------
# Category assignment
# --------------------------------------------------

async def assignment_page(update, context, channel_id, origin, page):
    channel = get_channel(channel_id)

    if not channel:
        await show(update, "Channel not found.")
        return

    assigned_ids = {
        row["category_id"] for row in get_channel_categories(channel_id)
    }

    keyboard = []

    for category in get_categories():
        cid = category["category_id"]
        prefix = "✓ " if cid in assigned_ids else "+ "

        keyboard.append([
            InlineKeyboardButton(
                prefix + category["name"],
                callback_data=f"toggle:{channel_id}:{cid}:{origin}:{page}",
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "Back to channel",
            callback_data=f"ch:{channel_id}:{origin}:{page}",
        )
    ])

    await show(
        update,
        f"Manage categories\n\n{channel['title']}\n\n"
        "Tap a category to assign or unassign it.",
        keyboard,
    )


async def toggle_assignment(update, context, channel_id, category_id, origin, page):
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
            # Once the user classifies a new destination, it leaves the queue.
            db.execute(
                "UPDATE channels SET newly_added = 0 WHERE id = ?",
                (str(channel_id),)
            )

    await assignment_page(
        update, context, channel_id, origin, page
    )


# --------------------------------------------------
# Search
# --------------------------------------------------

async def begin_search(update, context):
    context.user_data["awaiting"] = "search"

    await show(
        update,
        "Search channels\n\nSend a channel title or username.",
        [[InlineKeyboardButton("Home", callback_data="home")]],
    )


async def show_search_results(update, context, term):
    results = search_channels(term)
    keyboard = []

    for row in results:
        keyboard.append([
            InlineKeyboardButton(
                row["title"][:55],
                callback_data=f"ch:{row['id']}:0:0",
            )
        ])

    keyboard.append([
        InlineKeyboardButton("Search again", callback_data="search"),
        InlineKeyboardButton("Home", callback_data="home"),
    ])

    await show(
        update,
        f"Search results for: {term}\n\n"
        f"Found {len(results)} result(s).",
        keyboard,
    )


# --------------------------------------------------
# Category management
# --------------------------------------------------

async def begin_new_category(update, context):
    context.user_data["awaiting"] = "new_category"

    await show(
        update,
        "Send the name for your new category.",
        [[InlineKeyboardButton("Cancel", callback_data="cats")]],
    )


async def begin_rename(update, context, category_id):
    context.user_data["awaiting"] = "rename_category"
    context.user_data["rename_category_id"] = category_id

    await show(
        update,
        "Send the new category name.",
        [[InlineKeyboardButton("Cancel", callback_data=f"cat:{category_id}:0")]],
    )


async def confirm_delete(update, context, category_id):
    with connect_db() as db:
        row = db.execute(
            "SELECT name FROM categories WHERE category_id = ?",
            (category_id,)
        ).fetchone()

    if not row:
        await show(update, "Category not found.")
        return

    count = get_channel_count(category_id)

    keyboard = [
        [InlineKeyboardButton(
            f"Confirm delete ({count} assignments)",
            callback_data=f"delok:{category_id}",
        )],
        [InlineKeyboardButton(
            "Cancel",
            callback_data=f"cat:{category_id}:0",
        )],
    ]

    await show(
        update,
        f"Delete category: {row['name']}?\n\n"
        f"Affected channel assignments: {count}\n\n"
        "Only the category and its assignments will be deleted. "
        "Channel records will remain untouched.",
        keyboard,
    )


async def delete_category(update, context, category_id):
    with connect_db() as db:
        db.execute(
            "DELETE FROM categories WHERE category_id = ?",
            (category_id,)
        )

    await categories(update, context)


# --------------------------------------------------
# Text input
# --------------------------------------------------

async def receive_text(update, context):
    if not is_admin(update, context):
        return

    awaiting = context.user_data.get("awaiting")

    if not awaiting:
        return

    value = update.message.text.strip()
    context.user_data.pop("awaiting", None)

    if not value:
        await update.message.reply_text("Please send a non-empty value.")
        return

    if awaiting == "search":
        await show_search_results(update, context, value)

    elif awaiting == "new_category":
        if len(value) > 60:
            await update.message.reply_text(
                "Category name must be 60 characters or fewer."
            )
            return

        try:
            with connect_db() as db:
                db.execute(
                    "INSERT INTO categories (name, created_at) VALUES (?, datetime('now'))",
                    (value,)
                )
            await categories(update, context)
        except sqlite3.IntegrityError:
            await update.message.reply_text(
                "Could not create that category. Check for duplicates."
            )

    elif awaiting == "rename_category":
        category_id = context.user_data.pop("rename_category_id", None)

        if not category_id:
            return

        if len(value) > 60:
            await update.message.reply_text(
                "Category name must be 60 characters or fewer."
            )
            return

        with connect_db() as db:
            db.execute(
                "UPDATE categories SET name = ? WHERE category_id = ?",
                (value, category_id)
            )

        await category_page(update, context, category_id, 0)


# --------------------------------------------------
# Callback router
# --------------------------------------------------

async def callbacks(update, context):
    query = update.callback_query

    if not is_admin(update, context):
        await deny(update)
        return

    data = query.data

    # This handler owns its acknowledgement because it may show an alert.
    if data.startswith("open:"):
        await open_channel(update, context, data.split(":", 1)[1])
        return

    await query.answer()

    if data == "home":
        context.user_data.clear()
        await show(
            update,
            f"TG Manager\n\nYour Telegram channel library.\n\n"
            f"{get_total_channel_count()} destinations · "
            f"{len(get_categories())} categories · "
            f"{get_newly_added_count()} newly added",
            home_keyboard()
        )

    elif data == "cats":
        context.user_data.clear()
        await categories(update, context)

    elif data == "search":
        await begin_search(update, context)

    elif data == "newcat":
        await begin_new_category(update, context)

    elif data.startswith("cat:"):
        _, cid, page = data.split(":")
        context.user_data.clear()
        await category_page(update, context, int(cid), int(page))

    elif data.startswith("ch:"):
        _, channel_id, category_id, page = data.split(":")
        context.user_data.clear()
        await channel_page(
            update, context, channel_id, int(category_id), int(page)
        )

    elif data.startswith("newly:"):
        await system_category_page(update, context, "newly", int(data.split(":")[1]))

    elif data.startswith("uncat:"):
        await system_category_page(update, context, "uncat", int(data.split(":")[1]))

    elif data == "sync":
        await run_sync(update, context)

    elif data == "backup":
        await send_database_backup(update, context)

    elif data.startswith("assign:"):
        _, channel_id, origin, page = data.split(":")
        await assignment_page(
            update, context, channel_id, int(origin), int(page)
        )

    elif data.startswith("toggle:"):
        _, channel_id, cid, origin, page = data.split(":")
        await toggle_assignment(
            update, context, channel_id, int(cid), int(origin), int(page)
        )

    elif data.startswith("rename:"):
        await begin_rename(update, context, int(data.split(":")[1]))

    elif data.startswith("delete:"):
        await confirm_delete(update, context, int(data.split(":")[1]))

    elif data.startswith("delok:"):
        await delete_category(update, context, int(data.split(":")[1]))


# --------------------------------------------------
# Startup and shutdown
# --------------------------------------------------

async def post_init(application):
    ensure_schema()

    client = TelegramClient(
        SESSION_PATH,
        int(API_ID),
        API_HASH,
    )

    await client.connect()

    if not await client.is_user_authorized():
        await client.disconnect()
        raise RuntimeError("Existing Telethon account session is not authorized.")

    me = await client.get_me()

    application.bot_data["tg_client"] = client
    application.bot_data["admin_id"] = me.id

    logging.info("TG Manager administrator identity loaded.")
    logging.info("Bot startup initialization complete.")


async def post_shutdown(application):
    client = application.bot_data.get("tg_client")

    if client:
        await client.disconnect()


def main():
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", start))
    application.add_handler(CallbackQueryHandler(callbacks))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text)
    )

    logging.info("Starting TG Manager bot polling.")
    application.run_polling()


if __name__ == "__main__":
    main()
