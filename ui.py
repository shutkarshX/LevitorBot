"""
UI Components, Keyboard Builders, and Message Formatting for Snapit (TG-Manager).
"""
from typing import Optional, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup

from config import BRAND_NAME
from database import (
    get_total_channel_count,
    get_categories,
    get_newly_added_count,
    get_uncategorised_count,
)


def home_text() -> str:
    return (
        f"✨ {BRAND_NAME}\n"
        "Your Telegram space, sorted with a little sparkle.\n\n"
        f"📚 {get_total_channel_count()} destinations  ·  "
        f"🗂 {len(get_categories())} categories  ·  "
        f"🆕 {get_newly_added_count()} to review"
    )


def section_text(title: str, subtitle: Optional[str] = None) -> str:
    return f"✦ {title} ✦" + (f"\n\n{subtitle}" if subtitle else "")


def home_keyboard() -> List[List[InlineKeyboardButton]]:
    """Everyday library navigation on the home screen."""
    return [
        [InlineKeyboardButton(
            f"🆕 Newly Added · {get_newly_added_count()}",
            callback_data="newly:0"
        )],
        [
            InlineKeyboardButton("🗂 Browse categories", callback_data="cats"),
            InlineKeyboardButton(
                f"📭 Uncategorised · {get_uncategorised_count()}",
                callback_data="uncat:0"
            ),
        ],
        [InlineKeyboardButton("🔎 Search channels", callback_data="search")],
        [InlineKeyboardButton("⚙️ Management", callback_data="management")],
    ]


def management_keyboard() -> List[List[InlineKeyboardButton]]:
    """Administrative actions menu."""
    return [
        [InlineKeyboardButton("➕ Create category", callback_data="newcat")],
        [InlineKeyboardButton("✏️ Edit categories", callback_data="managecats")],
        [InlineKeyboardButton("🔄 Sync chat list", callback_data="sync")],
        [InlineKeyboardButton("💾 Download backup", callback_data="backup")],
        [InlineKeyboardButton("🏠 Back to home", callback_data="home")],
    ]


def is_admin(update: Update, context) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    return (
        user is not None
        and chat is not None
        and chat.type == "private"
        and user.id == context.application.bot_data.get("admin_id")
    )


async def deny(update: Update):
    if update.callback_query:
        await update.callback_query.answer("🔒 Snapit is private.", show_alert=True)
    elif update.effective_message:
        await update.effective_message.reply_text("🔒 Snapit is private.")


async def show(update: Update, text: str, keyboard: Optional[List[List[InlineKeyboardButton]]] = None):
    markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    if update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=markup)
    else:
        await update.effective_message.reply_text(text, reply_markup=markup)
