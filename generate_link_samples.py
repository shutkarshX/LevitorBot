import asyncio
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.types import PeerChannel

load_dotenv(Path(".env"))

api_id = int(os.environ["TG_API_ID"])
api_hash = os.environ["TG_API_HASH"]

DB_PATH = Path("data/tg_manager.db")
OUTPUT = Path("data/opening_link_samples.txt")
SESSION = "tg_manager_readonly"

async def main():
    db = sqlite3.connect(DB_PATH)
    rows = db.execute("""
        SELECT id, title
        FROM channels
        WHERE TRIM(COALESCE(username, '')) = ''
        ORDER BY title
    """).fetchall()
    db.close()

    client = TelegramClient(SESSION, api_id, api_hash)
    await client.connect()

    if not await client.is_user_authorized():
        print("Telegram session is not authorized.")
        await client.disconnect()
        return

    samples = []

    try:
        for channel_id, title in rows:
            try:
                peer = await client.get_input_entity(
                    PeerChannel(int(channel_id))
                )
                messages = await client.get_messages(peer, limit=1)

                if not messages:
                    continue

                message = messages[0]
                if not message or not message.id:
                    continue

                link = f"https://t.me/c/{channel_id}/{message.id}"
                samples.append((title, link))

                if len(samples) == 5:
                    break

            except Exception:
                continue

    finally:
        await client.disconnect()

    if not samples:
        print("No private-channel samples could be generated.")
        return

    content = [
        "TG MANAGER - PRIVATE CHANNEL LINK TEST",
        "Open these links using the Telegram account that has channel access.",
        ""
    ]

    for index, (title, link) in enumerate(samples, 1):
        content.extend([
            f"{index}. {title}",
            link,
            ""
        ])

    OUTPUT.write_text("\n".join(content), encoding="utf-8")

    print("Generated samples:", len(samples))
    print("Saved locally to:", OUTPUT.resolve())
    print("No channel records or category assignments were changed.")

asyncio.run(main())
