import os
from pathlib import Path
from dotenv import load_dotenv
from telegram import Bot

load_dotenv(Path(".env"))

token = os.getenv("BOT_TOKEN")
if not token:
    raise SystemExit("BOT_TOKEN missing")

import asyncio

async def main():
    bot = Bot(token)
    me = await bot.get_me()
    print("Connection successful!")
    print("Bot name:", me.first_name)
    print("Bot username:", "@" + me.username)

asyncio.run(main())
