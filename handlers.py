"""
Telegram Bot Update Handlers and Callback Routing for Snapit (TG-Manager).
"""
import asyncio
import html
import logging
import sqlite3
import tempfile
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import DB_PATH, PAGE_SIZE
import database as db
from telegram_client import sync_main_dialogs, resolve_channel_link
from terabox import (
    extract_terabox_url,
    resolve_terabox_link,
    download_terabox_file,
    get_terabox_cookie,
    format_bytes,
    TeraBoxResult,
)
from ui import (
    home_text,
    section_text,
    home_keyboard,
    management_keyboard,
    is_admin,
    deny,
    show,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------
# Commands
# --------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context):
        await deny(update)
        return
    context.user_data.clear()
    await show(update, home_text(), home_keyboard())


async def terabox_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context):
        await deny(update)
        return
    cookie = get_terabox_cookie()
    cookie_status = "✅ Configured (Active)" if cookie else "⚠️ Not configured"
    text = (
        "🎬 <b>TeraBox In-Chat Video Player & Downloader</b>\n\n"
        "Send any TeraBox share link directly to this chat to watch or download!\n\n"
        f"🔑 <b>TeraBox Cookie Status:</b> {cookie_status}\n\n"
        "⚙️ <b>How to enable direct in-Telegram video playback:</b>\n"
        "1. Open TeraBox in browser (PC or mobile) and copy your <code>ndus</code> cookie.\n"
        "2. Send <code>/cookie &lt;your_ndus_token&gt;</code> in this chat.\n\n"
        "💡 <b>Key advantages of the Cookie method:</b>\n"
        "• <b>No PC needed</b>: Your PC does NOT need to stay on. The server runs 24/7.\n"
        "• <b>No monthly limit</b>: Direct connection has NO 1,000 requests cap.\n"
        "• <b>Long-lasting</b>: The cookie remains active for months."
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def cookie_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context):
        await deny(update)
        return

    args = context.args
    if not args:
        current_cookie = get_terabox_cookie()
        if current_cookie:
            masked = current_cookie[:6] + "..." + current_cookie[-6:] if len(current_cookie) > 12 else "active"
            msg = (
                f"🔑 <b>TeraBox Cookie Status: Active</b>\n"
                f"Current token: <code>{masked}</code>\n\n"
                "To update your cookie, send:\n"
                "<code>/cookie &lt;your_new_ndus_value&gt;</code>\n\n"
                "💡 <i>Reminder: Your PC does NOT need to stay on. Once saved, the server uses this token 24/7.</i>"
            )
        else:
            msg = (
                "🔑 <b>TeraBox Cookie Setup</b>\n\n"
                "No TeraBox cookie is currently configured.\n\n"
                "<b>How to get your cookie:</b>\n"
                "1. Open TeraBox in your browser (PC or phone) and log in.\n"
                "2. Copy the <code>ndus</code> cookie value.\n"
                "3. Send it here: <code>/cookie &lt;ndus_token&gt;</code>\n\n"
                "✅ Once configured, you can watch TeraBox videos directly inside Telegram without any redirects!"
            )
        await update.message.reply_text(msg, parse_mode="HTML")
        return

    token = " ".join(args).strip().strip('"').strip("'")
    if token.startswith("ndus="):
        token = token[5:].strip()

    if len(token) < 10:
        await update.message.reply_text("⚠️ The provided token seems too short. Make sure you copied the full ndus cookie.")
        return

    db.set_setting("terabox_cookie", token)
    logger.info("TeraBox cookie successfully saved by admin.")
    await update.message.reply_text(
        "✅ <b>TeraBox Cookie saved successfully!</b>\n\n"
        "🎬 Direct in-chat Telegram video playback is now active.\n"
        "Send any TeraBox link to try it out!\n\n"
        "💡 <i>Your PC does NOT need to stay on; this token works 24/7 on your hosting server.</i>",
        parse_mode="HTML",
    )



# --------------------------------------------------
# Categories Browsing
# --------------------------------------------------

async def categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.get_categories()
    keyboard = []
    for row in rows:
        count = db.get_channel_count(row["category_id"])
        keyboard.append([
            InlineKeyboardButton(
                f"{row['name']} ({count})",
                callback_data=f"cat:{row['category_id']}:0",
            )
        ])
    keyboard.append([
        InlineKeyboardButton("🔎 Search", callback_data="search"),
        InlineKeyboardButton("🏠 Home", callback_data="home"),
    ])
    await show(update, section_text("Your categories", "Pick a shelf to explore ↓"), keyboard)


async def category_page(update: Update, context: ContextTypes.DEFAULT_TYPE, category_id: int, page: int):
    category = db.get_category(category_id)
    if not category:
        await show(update, "That category couldn't be found.", [
            [InlineKeyboardButton("🗂 Categories", callback_data="cats")]
        ])
        return

    total = db.get_channel_count(category_id)
    channel_list = db.get_category_channels(category_id, page)

    keyboard = []
    for channel in channel_list:
        keyboard.append([
            InlineKeyboardButton(
                f"▣ Channel · {channel['title'][:43]}",
                callback_data=f"ch:{channel['id']}:{category_id}:{page}",
            )
        ])

    navigation = []
    if page > 0:
        navigation.append(InlineKeyboardButton("Previous", callback_data=f"cat:{category_id}:{page - 1}"))
    if (page + 1) * PAGE_SIZE < total:
        navigation.append(InlineKeyboardButton("Next", callback_data=f"cat:{category_id}:{page + 1}"))
    if navigation:
        keyboard.append(navigation)

    keyboard.append([InlineKeyboardButton("⬅️ All categories", callback_data="cats")])

    text = f"🗂 {category['name']}\n{total} assigned channel(s)\n\n"
    text += "Choose a channel to open ↓" if channel_list else "Nothing on this shelf yet.\nUse search to add a channel."
    await show(update, text, keyboard)


async def system_category_page(update: Update, context: ContextTypes.DEFAULT_TYPE, kind: str, page: int):
    total = db.get_system_channel_count(kind)
    channel_list = db.get_system_channels(kind, page)
    title = "Newly Added" if kind == "newly" else "Uncategorised"
    icon = "🆕" if kind == "newly" else "📭"
    keyboard = []

    for channel in channel_list:
        keyboard.append([InlineKeyboardButton(
            f"▣ Channel · {channel['title'][:43]}",
            callback_data=f"ch:{channel['id']}:0:{page}"
        )])

    navigation = []
    if page > 0:
        navigation.append(InlineKeyboardButton("Previous", callback_data=f"{kind}:{page - 1}"))
    if (page + 1) * PAGE_SIZE < total:
        navigation.append(InlineKeyboardButton("Next", callback_data=f"{kind}:{page + 1}"))
    if navigation:
        keyboard.append(navigation)

    keyboard.append([InlineKeyboardButton("🏠 Home", callback_data="home")])
    message = (
        f"{icon} {title}  ·  {total} destination(s)\n\n"
        + ("Tap a destination to peek inside ↓" if channel_list else "All clear here for now ✨")
    )
    await show(update, message, keyboard)


# --------------------------------------------------
# Channel Details & Opening
# --------------------------------------------------

async def channel_page(update: Update, context: ContextTypes.DEFAULT_TYPE, channel_id: str, category_id: int = 0, page: int = 0):
    channel = db.get_channel(channel_id)
    if not channel:
        await show(update, "That channel couldn't be found.")
        return

    assigned = db.get_channel_categories(channel_id)
    safe_title = html.escape(channel["title"])
    safe_type = html.escape(channel["type"])
    text = (
        f"<b>{safe_title}</b>\n\n"
        f"🏷 <b>Type:</b> {safe_type}\n"
        f"🔗 <b>Username:</b> @{html.escape(channel['username'])}"
        if channel["username"]
        else f"<b>{safe_title}</b>\n\n🏷 <b>Type:</b> {safe_type}\n🔗 <i>Private destination (no public username)</i>"
    )
    text += "\n\n<b>Assigned Categories:</b>\n"
    text += "\n".join(f"• {html.escape(row['name'])}" for row in assigned) if assigned else "<i>None</i>"

    keyboard = [
        [InlineKeyboardButton("↗️ Open in Telegram", callback_data=f"open:{channel_id}")],
        [InlineKeyboardButton("🗂 Manage categories", callback_data=f"assign:{channel_id}:{category_id}:{page}")],
    ]

    if category_id:
        keyboard.append([InlineKeyboardButton("⬅️ Back to list", callback_data=f"cat:{category_id}:{page}")])
    else:
        keyboard.append([InlineKeyboardButton("⬅️ Back to search", callback_data="search")])

    keyboard.append([InlineKeyboardButton("🏠 Home", callback_data="home")])
    await show(update, text, keyboard)


async def open_channel(update: Update, context: ContextTypes.DEFAULT_TYPE, channel_id: str):
    channel = db.get_channel(channel_id)
    if not channel:
        await update.callback_query.answer("That channel couldn't be found.", show_alert=True)
        return

    client = context.application.bot_data.get("tg_client")
    url, error = await resolve_channel_link(client, channel)
    if error:
        await update.callback_query.answer(error, show_alert=True)
        return

    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        f"Open {channel['title']}:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↗️ Open in Telegram", url=url)]]),
    )


# --------------------------------------------------
# Category Assignment
# --------------------------------------------------

async def assignment_page(update: Update, context: ContextTypes.DEFAULT_TYPE, channel_id: str, origin: int, page: int):
    channel = db.get_channel(channel_id)
    if not channel:
        await show(update, "That channel couldn't be found.")
        return

    assigned_ids = {row["category_id"] for row in db.get_channel_categories(channel_id)}
    keyboard = []
    for category in db.get_categories():
        cid = category["category_id"]
        prefix = "✓ " if cid in assigned_ids else "+ "
        keyboard.append([
            InlineKeyboardButton(
                prefix + category["name"],
                callback_data=f"toggle:{channel_id}:{cid}:{origin}:{page}",
            )
        ])

    keyboard.append([InlineKeyboardButton("Back to channel", callback_data=f"ch:{channel_id}:{origin}:{page}")])
    await show(update, f"Manage categories\n\n{channel['title']}\n\nTap a shelf to add or remove it.", keyboard)


async def toggle_assignment(update: Update, context: ContextTypes.DEFAULT_TYPE, channel_id: str, category_id: int, origin: int, page: int):
    db.toggle_channel_category(channel_id, category_id)
    await assignment_page(update, context, channel_id, origin, page)


# --------------------------------------------------
# Category Management (CRUD)
# --------------------------------------------------

async def manage_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.get_categories()
    keyboard = []
    for row in rows:
        count = db.get_channel_count(row["category_id"])
        keyboard.append([InlineKeyboardButton(f"{row['name']} · {count}", callback_data=f"managecat:{row['category_id']}")])
    keyboard.append([InlineKeyboardButton("⬅️ Management", callback_data="management")])
    await show(update, section_text("Edit categories", "Choose a category to rename or delete."), keyboard)


async def category_management_page(update: Update, context: ContextTypes.DEFAULT_TYPE, category_id: int):
    category = db.get_category(category_id)
    if not category:
        await manage_categories(update, context)
        return
    count = db.get_channel_count(category_id)
    keyboard = [
        [InlineKeyboardButton("✏️ Rename", callback_data=f"rename:{category_id}")],
        [InlineKeyboardButton("🗑 Delete", callback_data=f"delete:{category_id}")],
        [InlineKeyboardButton("⬅️ Edit categories", callback_data="managecats")],
    ]
    await show(update, f"Edit category\n\n{category['name']}\n{count} channel assignment(s)", keyboard)


async def begin_new_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["awaiting"] = "new_category"
    await show(update, "➕ Name your new shelf\n\nSend a category name to create it.", [[InlineKeyboardButton("↩️ Cancel", callback_data="cats")]])


async def begin_rename(update: Update, context: ContextTypes.DEFAULT_TYPE, category_id: int):
    context.user_data["awaiting"] = "rename_category"
    context.user_data["rename_category_id"] = category_id
    await show(update, "✏️ Rename this shelf\n\nSend its new name.", [[InlineKeyboardButton("↩️ Cancel", callback_data=f"managecat:{category_id}")]])


async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE, category_id: int):
    category = db.get_category(category_id)
    if not category:
        await show(update, "That category couldn't be found.")
        return
    count = db.get_channel_count(category_id)
    keyboard = [
        [InlineKeyboardButton(f"Yes, delete · {count} assignments", callback_data=f"delok:{category_id}")],
        [InlineKeyboardButton("Cancel", callback_data=f"managecat:{category_id}")],
    ]
    await show(
        update,
        f"Delete category: {category['name']}?\n\n⚠️ Affected channel assignments: {count}\n\n"
        "Only this shelf and its assignments will be removed. Your channel records will stay safe.",
        keyboard,
    )


async def delete_category_action(update: Update, context: ContextTypes.DEFAULT_TYPE, category_id: int):
    db.delete_category(category_id)
    await manage_categories(update, context)


# --------------------------------------------------
# Search
# --------------------------------------------------

async def begin_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["awaiting"] = "search"
    await show(update, "🔎 Find a channel\n\nSend its name or @username and I'll look it up.", [[InlineKeyboardButton("🏠 Home", callback_data="home")]])


async def show_search_results(update: Update, context: ContextTypes.DEFAULT_TYPE, term: str):
    results = db.search_channels(term)
    keyboard = []
    for row in results:
        keyboard.append([InlineKeyboardButton(f"▣ Channel · {row['title'][:43]}", callback_data=f"ch:{row['id']}:0:0")])
    keyboard.append([
        InlineKeyboardButton("🔎 Search again", callback_data="search"),
        InlineKeyboardButton("🏠 Home", callback_data="home"),
    ])
    await show(update, f"🔎 Results for “{term}”\n\nFound {len(results)} match(es).", keyboard)


# --------------------------------------------------
# Sync & Database Backup
# --------------------------------------------------

async def run_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.edit_message_text(
        "🔄 Syncing your main chat list…\n\n"
        "Your DMs, bot chats and archived chats stay untouched."
    )
    try:
        client = context.application.bot_data["tg_client"]
        result = await sync_main_dialogs(client)
    except Exception:
        logger.exception("Main chat-list sync failed.")
        await query.message.reply_text(
            "⚠️ Sync failed. Your existing records and category assignments "
            "were not intentionally removed. Check the bot log and try again."
        )
        return

    await query.message.reply_text(
        "✨ Sync complete!\n\n"
        f"👀 Checked: {result['seen']}\n"
        f"🆕 Newly found: {result['added']}\n"
        f"🔁 Refreshed: {result['updated']}\n"
        f"🗑 Removed from directory: {result['removed']}\n"
        f"📥 Waiting for review: {result['newly_added']}",
        reply_markup=InlineKeyboardMarkup(home_keyboard())
    )


async def send_database_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        with tempfile.TemporaryDirectory(prefix="tg_manager_backup_") as temp_dir:
            backup_path = Path(temp_dir) / filename
            with closing(sqlite3.connect(DB_PATH, timeout=30)) as source:
                with closing(sqlite3.connect(backup_path, timeout=30)) as destination:
                    source.backup(destination)
                    integrity = destination.execute("PRAGMA integrity_check").fetchone()[0]

            if integrity != "ok":
                raise sqlite3.DatabaseError(f"Backup integrity check failed: {integrity}")

            size = backup_path.stat().st_size
            with backup_path.open("rb") as backup_file:
                await message.reply_document(
                    document=backup_file,
                    filename=filename,
                    caption=(
                        "✨ Snapit database backup\n"
                        f"Created: {timestamp}\n"
                        f"Size: {size:,} bytes\n"
                        "Integrity check: OK"
                    ),
                )
        logger.info("Database backup sent to admin (%s bytes).", size)
    except Exception:
        logger.exception("Could not create or send database backup.")
        await message.reply_text("💾 Snapit backup failed. Check the hosting logs and try again.")


# --------------------------------------------------
# TeraBox Link Handler
# --------------------------------------------------

async def handle_terabox_message(update: Update, context: ContextTypes.DEFAULT_TYPE, share_url: str):
    logger.info("Processing detected TeraBox link: %s", share_url)
    status_msg = await update.message.reply_text("⏳ Processing TeraBox link…")

    try:
        result = await asyncio.to_thread(resolve_terabox_link, share_url)
    except Exception as exc:
        logger.exception("Failed during resolve_terabox_link: %s", exc)
        result = TeraBoxResult(
            url=share_url,
            title="TeraBox Media File",
            size=0,
            size_formatted="Stream / Direct Download",
            watch_url=None,
            download_url=None,
            iteraplay_url="https://iteraplay.com",
            success=False,
        )

    # 1. Direct download & in-chat video streaming available
    if result.download_url:
        temp_dir = Path("data") / "temp_media"
        temp_dir.mkdir(parents=True, exist_ok=True)

        safe_name = "".join(c for c in result.title if c.isalnum() or c in "._- ")[:60].strip() or "video.mp4"
        if not safe_name.lower().endswith((".mp4", ".mkv", ".webm", ".mov", ".avi")):
            safe_name += ".mp4"

        tmp_path = temp_dir / f"{int(time.time())}_{safe_name}"
        thumb_path = None

        try:
            await status_msg.edit_text(f"📥 Downloading '{result.title}' ({result.size_formatted}) for in-chat playback…")

            cookie = result.cookie_used or get_terabox_cookie()
            await asyncio.to_thread(download_terabox_file, result.download_url, tmp_path, cookie)

            # Download preview thumbnail if available
            if result.thumbnail_url:
                try:
                    thumb_candidate = temp_dir / f"thumb_{int(time.time())}.jpg"
                    await asyncio.to_thread(download_terabox_file, result.thumbnail_url, thumb_candidate, cookie)
                    if thumb_candidate.exists() and thumb_candidate.stat().st_size > 0:
                        thumb_path = thumb_candidate
                except Exception as t_err:
                    logger.debug("Could not download video thumbnail: %s", t_err)

            file_size = tmp_path.stat().st_size if tmp_path.exists() else 0
            if file_size > 0:
                caption = (
                    f"🎬 <b>{result.title}</b>\n\n"
                    f"📦 <b>Size:</b> {result.size_formatted}\n"
                    f"⚡ <b>Playback:</b> Telegram Native Stream"
                )
                video_buttons = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🌐 Original Link", url=share_url),
                        InlineKeyboardButton("▶️ Open in iTeraPlay", url=result.iteraplay_url),
                    ]
                ])

                uploaded = False

                # Attempt 1: Upload directly via Bot API with 60s timeout
                if file_size <= 50 * 1024 * 1024:
                    await status_msg.edit_text(f"🚀 Delivering '{html.escape(result.title)}' ({format_bytes(file_size)}) to Telegram…")
                    try:
                        with open(tmp_path, "rb") as video_file:
                            thumb_file = open(thumb_path, "rb") if thumb_path and thumb_path.exists() else None
                            try:
                                await update.message.reply_video(
                                    video=video_file,
                                    thumbnail=thumb_file,
                                    caption=caption,
                                    parse_mode="HTML",
                                    supports_streaming=True,
                                    filename=safe_name,
                                    reply_markup=video_buttons,
                                    write_timeout=60,
                                    read_timeout=60,
                                )
                                uploaded = True
                            finally:
                                if thumb_file:
                                    thumb_file.close()
                    except Exception as bot_err:
                        logger.warning("Primary Bot API upload attempt hit timeout/issue (%s), retrying once...", bot_err)
                        try:
                            with open(tmp_path, "rb") as video_file:
                                await context.bot.send_video(
                                    chat_id=update.effective_chat.id,
                                    video=video_file,
                                    caption=caption,
                                    parse_mode="HTML",
                                    supports_streaming=True,
                                    filename=safe_name,
                                    reply_markup=video_buttons,
                                    write_timeout=60,
                                    read_timeout=60,
                                )
                                uploaded = True
                        except Exception as retry_err:
                            logger.warning("Retry upload attempt also failed: %s", retry_err)

                # Attempt 2: If over 50MB (Bot API limit) or Bot API unreachable, deliver via Telethon
                if not uploaded and file_size > 50 * 1024 * 1024:
                    tg_client = context.bot_data.get("tg_client")
                    if tg_client:
                        await status_msg.edit_text(f"🚀 Delivering large media ({result.size_formatted}) via Telethon…")
                        chat_id = update.effective_chat.id
                        await tg_client.send_file(
                            chat_id,
                            str(tmp_path),
                            thumb=str(thumb_path) if thumb_path and thumb_path.exists() else None,
                            caption=f"🎬 **{result.title}**\n\n📦 **Size:** {result.size_formatted}\n⚡ **Playback:** Telegram Native Stream",
                            supports_streaming=True,
                        )
                        uploaded = True

                if uploaded:
                    try:
                        await status_msg.delete()
                    except Exception:
                        pass
                    return
                else:
                    await status_msg.edit_text(
                        f"🎬 <b>{result.title}</b> ({result.size_formatted})\n\n"
                        f"Could not upload video directly to chat.\n"
                        f"You can watch or download it ad-free below:",
                        parse_mode="HTML",
                        reply_markup=video_buttons,
                    )
                    return

        except Exception as e:
            logger.exception("Error while downloading/sending video: %s", e)
            await status_msg.edit_text(f"⚠️ Could not stream video directly ({e}). Providing direct web options below:")
        finally:
            try:
                if tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            try:
                if thumb_path and thumb_path.exists():
                    thumb_path.unlink(missing_ok=True)
            except Exception:
                pass

    # 2. If direct video couldn't be downloaded (e.g. need cookie / verification):
    keyboard = []
    action_row = []
    if result.watch_url:
        action_row.append(InlineKeyboardButton("▶️ Watch Online", url=result.watch_url))
    if result.download_url:
        action_row.append(InlineKeyboardButton("⬇️ Fast Download", url=result.download_url))

    if action_row:
        keyboard.append(action_row)

    keyboard.append([InlineKeyboardButton("🌐 Open in iTeraPlay", url=result.iteraplay_url)])

    cookie = get_terabox_cookie()
    if not cookie:
        caption = (
            "🎬 <b>TeraBox Media Detected</b>\n\n"
            f"📁 <b>Title:</b> {result.title}\n"
            f"📦 <b>Size:</b> {result.size_formatted}\n"
            f"🔗 <b>Link:</b> {share_url}\n\n"
            "⚠️ <b>Direct In-Chat Playback Setup:</b>\n"
            "To watch this video directly inside Telegram without any website redirect, "
            "add your TeraBox <code>ndus</code> cookie once:\n\n"
            "👉 Send: <code>/cookie &lt;your_ndus_value&gt;</code>\n\n"
            "💡 <b>Good to know:</b>\n"
            "• You only do this <b>once</b> (lasts for months)\n"
            "• Your PC does <b>NOT</b> need to stay on\n"
            "• There is <b>NO 1,000 monthly limit</b> (unlimited)\n\n"
            "<i>In the meantime, you can watch ad-free on iTeraPlay below:</i>"
        )
    else:
        caption = (
            "🎬 <b>TeraBox Media Detected</b>\n\n"
            f"📁 <b>Title:</b> {result.title}\n"
            f"📦 <b>Size:</b> {result.size_formatted}\n"
            f"🔗 <b>Link:</b> {share_url}\n\n"
            "💡 TeraBox is currently requesting verification for this specific link. "
            "You can watch and download ad-free directly on iTeraPlay below:"
        )

    await status_msg.edit_text(
        caption,
        reply_markup=InlineKeyboardMarkup(keyboard),
        disable_web_page_preview=True,
        parse_mode="HTML",
    )


# --------------------------------------------------
# Message Text Handler
# --------------------------------------------------

async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update, context):
        return

    raw_text = (update.message.text or update.message.caption or "").strip()
    if not raw_text:
        return

    logger.info("Received message from admin: %s", raw_text[:80])

    # 1. Automatic TeraBox link detection
    tb_url = extract_terabox_url(raw_text)
    if tb_url:
        logger.info("Extracted TeraBox URL: %s", tb_url)
        await handle_terabox_message(update, context, tb_url)
        return

    # 2. General menu input state handling
    awaiting = context.user_data.get("awaiting")
    if awaiting:
        value = raw_text
        context.user_data.pop("awaiting", None)

        if awaiting == "search":
            await show_search_results(update, context, value)

        elif awaiting == "new_category":
            if len(value) > 60:
                await update.message.reply_text("Keep the category name under 60 characters.")
                return
            try:
                db.create_category(value)
                await categories(update, context)
            except sqlite3.IntegrityError:
                await update.message.reply_text("Couldn't create that shelf. Check whether its name already exists.")

        elif awaiting == "rename_category":
            category_id = context.user_data.pop("rename_category_id", None)
            if not category_id:
                return
            if len(value) > 60:
                await update.message.reply_text("Keep the category name under 60 characters.")
                return
            db.rename_category(category_id, value)
            await category_management_page(update, context, category_id)

        elif awaiting == "cookie":
            token = value.strip().strip('"').strip("'")
            if token.startswith("ndus="):
                token = token[5:].strip()
            if len(token) < 10:
                await update.message.reply_text("⚠️ The token seems too short. Make sure you copied the full ndus value.")
                return
            db.set_setting("terabox_cookie", token)
            logger.info("TeraBox cookie updated via awaiting state.")
            await update.message.reply_text(
                "✅ <b>TeraBox Cookie saved successfully!</b>\n\n"
                "🎬 Direct in-chat Telegram video playback is now active.\n"
                "Send any TeraBox link to try it!",
                parse_mode="HTML",
            )
        return

    # 3. Informative response if user sends non-menu text
    if raw_text == "/cancel":
        context.user_data.clear()
        await update.message.reply_text("Action cancelled.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Home", callback_data="home")]]))
        return

    if raw_text.startswith("http://") or raw_text.startswith("https://"):
        await update.message.reply_text(
            "⚠️ This link was not recognized as a supported TeraBox link.\n"
            "Please send a TeraBox share link (e.g. terabox.com, 1024tera.com, etc.)."
        )
    else:
        await update.message.reply_text(
            "✨ Send me any TeraBox link to watch or download, or send /start to open your library."
        )


# --------------------------------------------------
# Callback Router
# --------------------------------------------------

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(update, context):
        await deny(update)
        return

    data = query.data

    if data.startswith("open:"):
        await open_channel(update, context, data.split(":", 1)[1])
        return

    await query.answer()

    if data == "home":
        context.user_data.clear()
        await show(update, home_text(), home_keyboard())

    elif data == "tb_info":
        context.user_data.clear()
        cookie = get_terabox_cookie()
        cookie_status = "Active ✅" if cookie else "Not Set ⚠️"
        text = (
            "🎬 <b>TeraBox Ad-Free Player</b>\n\n"
            "Send any TeraBox share link directly to this chat to play or download without ads!\n\n"
            f"🔑 <b>Cookie Status:</b> {cookie_status}\n"
            "⚡ <b>Playback Engine:</b> Telegram Native Stream (In-App Player)\n\n"
            "💡 <i>Tip: Send /cookie &lt;token&gt; to update your token anytime.</i>"
        )
        keyboard = [
            [InlineKeyboardButton("🔑 Update Cookie", callback_data="set_cookie_prompt")],
            [InlineKeyboardButton("🏠 Back to Home", callback_data="home")],
        ]
        await show(update, text, keyboard)

    elif data == "set_cookie_prompt":
        context.user_data["awaiting"] = "cookie"
        text = (
            "🔑 <b>Update TeraBox Cookie</b>\n\n"
            "Send your <code>ndus</code> cookie value directly in this chat, or send /cancel to return."
        )
        keyboard = [[InlineKeyboardButton("↩️ Cancel", callback_data="tb_info")]]
        await show(update, text, keyboard)

    elif data == "cats":
        context.user_data.clear()
        await categories(update, context)

    elif data == "management":
        context.user_data.clear()
        await show(update, "⚙️ Your toolkit\n\nPick an action:", management_keyboard())

    elif data == "search":
        await begin_search(update, context)

    elif data == "newcat":
        await begin_new_category(update, context)

    elif data == "managecats":
        context.user_data.clear()
        await manage_categories(update, context)

    elif data.startswith("managecat:"):
        await category_management_page(update, context, int(data.split(":")[1]))

    elif data.startswith("cat:"):
        _, cid, page = data.split(":")
        context.user_data.clear()
        await category_page(update, context, int(cid), int(page))

    elif data.startswith("ch:"):
        _, channel_id, category_id, page = data.split(":")
        context.user_data.clear()
        await channel_page(update, context, channel_id, int(category_id), int(page))

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
        await assignment_page(update, context, channel_id, int(origin), int(page))

    elif data.startswith("toggle:"):
        _, channel_id, cid, origin, page = data.split(":")
        await toggle_assignment(update, context, channel_id, int(cid), int(origin), int(page))

    elif data.startswith("rename:"):
        await begin_rename(update, context, int(data.split(":")[1]))

    elif data.startswith("delete:"):
        await confirm_delete(update, context, int(data.split(":")[1]))

    elif data.startswith("delok:"):
        await delete_category_action(update, context, int(data.split(":")[1]))
