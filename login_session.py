"""
Helper script to authenticate and generate user session file.
Run this locally on your PC before uploading the session to your hosting panel (e.g. SillyDev / Pterodactyl).
"""
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from telethon import TelegramClient

from config import SESSION_PATH

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")

API_ID = os.getenv("TG_API_ID")
API_HASH = os.getenv("TG_API_HASH")

if not API_ID or not API_HASH:
    raise SystemExit("Error: Missing TG_API_ID or TG_API_HASH in .env file.")


async def main():
    print("=" * 60)
    print("      LEViTORBOT — TELETHON SESSION AUTHENTICATION")
    print("=" * 60)
    print(f"Target session: {SESSION_PATH}.session\n")

    client = TelegramClient(SESSION_PATH, int(API_ID), API_HASH)
    await client.start()

    if not await client.is_user_authorized():
        print("❌ Authorization failed.")
        await client.disconnect()
        return

    me = await client.get_me()
    print("\n✅ Session successfully authorized!")
    print(f"Logged in user : {me.first_name} {me.last_name or ''}".strip())
    print(f"Username       : @{me.username or 'No username'}")
    print(f"Telegram ID    : {me.id}")
    print(f"Session file   : {SESSION_PATH}.session")
    print("\n📋 Next step:")
    print(f"Upload '{Path(SESSION_PATH).name}.session' to your hosting panel root folder.")
    print("=" * 60)

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
