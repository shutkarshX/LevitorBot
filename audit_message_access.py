import asyncio
import sqlite3
from pathlib import Path
from telethon import TelegramClient
from telethon.tl.types import PeerChannel
from dotenv import load_dotenv
import os

load_dotenv(Path(".env"))

api_id = int(os.environ["TG_API_ID"])
api_hash = os.environ["TG_API_HASH"]

async def main():
    client = TelegramClient(
        "tg_manager_readonly",
        api_id,
        api_hash
    )

    await client.connect()

    if not await client.is_user_authorized():
        print("Session is not authorized.")
        await client.disconnect()
        return

    db = sqlite3.connect("data/tg_manager.db")
    rows = db.execute("SELECT id FROM channels").fetchall()

    checked = 0
    accessible = 0
    with_messages = 0
    no_messages = 0
    errors = 0

    for (channel_id,) in rows:
        try:
            peer = await client.get_input_entity(
                PeerChannel(int(channel_id))
            )
            messages = await client.get_messages(peer, limit=1)

            checked += 1
            accessible += 1

            if messages:
                with_messages += 1
            else:
                no_messages += 1

        except Exception:
            checked += 1
            errors += 1

    print("\n=== DESTINATION ACCESS AUDIT ===")
    print("Checked:", checked)
    print("Accessible:", accessible)
    print("With messages:", with_messages)
    print("No messages:", no_messages)
    print("Errors:", errors)

    db.close()
    await client.disconnect()

asyncio.run(main())
