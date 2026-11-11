"""
Snapit (TG-Manager) Bot Main Entry Point.
Assembles Telegram Application, registers command and callback handlers, and runs polling.
"""
import logging
from telegram import BotCommand
from telegram.request import HTTPXRequest
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from config import BOT_TOKEN, setup_logging
import database as db
from telegram_client import create_telethon_client
from handlers import (
    start,
    terabox_help_command,
    cookie_command,
    callbacks,
    receive_text,
)

setup_logging()
logger = logging.getLogger(__name__)


async def post_init(application: Application):
    await application.bot.set_my_commands([
        BotCommand("start", "Open Snapit"),
        BotCommand("menu", "Open the main menu"),
        BotCommand("terabox", "TeraBox player info and status"),
        BotCommand("cookie", "Set or check TeraBox cookie"),
    ])

    db.ensure_schema()

    client = create_telethon_client()
    await client.connect()

    if not await client.is_user_authorized():
        await client.disconnect()
        raise RuntimeError(
            "Telethon account session is not authorized. "
            "Run 'python login_session.py' locally first and upload 'tg_manager_readonly.session'."
        )

    me = await client.get_me()
    application.bot_data["tg_client"] = client
    application.bot_data["admin_id"] = me.id

    logger.info("Snapit administrator identity loaded: %s (ID: %s)", me.first_name, me.id)
    logger.info("Bot startup initialization complete.")


async def post_shutdown(application: Application):
    client = application.bot_data.get("tg_client")
    if client:
        await client.disconnect()
        logger.info("Telethon client disconnected.")


def main():
    request = HTTPXRequest(
        connection_pool_size=16,
        connect_timeout=60.0,
        read_timeout=300.0,
        write_timeout=300.0,
        pool_timeout=60.0,
    )
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .request(request)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", start))
    application.add_handler(CommandHandler("terabox", terabox_help_command))
    application.add_handler(CommandHandler("cookie", cookie_command))
    application.add_handler(CommandHandler("setcookie", cookie_command))
    application.add_handler(CallbackQueryHandler(callbacks))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text))

    logger.info("Starting Snapit bot polling.")
    application.run_polling()


if __name__ == "__main__":
    main()
