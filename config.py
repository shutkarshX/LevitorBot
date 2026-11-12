"""
Configuration and Environment Settings for LevitorBot.
"""
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent

# Support seamless transition from legacy tg_manager files to levitor
_legacy_db = BASE / "data" / "tg_manager.db"
_new_db = BASE / "data" / "levitor.db"
DB_PATH = _legacy_db if (not _new_db.exists() and _legacy_db.exists()) else _new_db

_legacy_session = BASE / "tg_manager_readonly.session"
_new_session = BASE / "levitor_readonly.session"
SESSION_PATH = (
    str(BASE / "tg_manager_readonly")
    if (not _new_session.exists() and _legacy_session.exists())
    else str(BASE / "levitor_readonly")
)

load_dotenv(BASE / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = os.getenv("TG_API_ID")
API_HASH = os.getenv("TG_API_HASH")

if not BOT_TOKEN or not API_ID or not API_HASH:
    raise RuntimeError("Required environment configuration (BOT_TOKEN, TG_API_ID, TG_API_HASH) is missing in .env.")

PAGE_SIZE = 8
BRAND_NAME = "LevitorBot"

DEFAULT_CATEGORIES = [
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


def setup_logging():
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telethon").setLevel(logging.WARNING)
