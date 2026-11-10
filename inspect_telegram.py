
import csv
from pathlib import Path

from telethon.sync import TelegramClient
from telethon.tl.types import Channel

BASE_DIR = Path(__file__).resolve().parent
CSV_FILE = BASE_DIR / "channel_inventory.csv"

print("=" * 55)
print("          TG MANAGER - FULL CHANNEL INVENTORY")
print("=" * 55)

from dotenv import load_dotenv
import os

load_dotenv()

api_id = int(os.getenv("TG_API_ID"))
api_hash = os.getenv("TG_API_HASH")

if not api_id or not api_hash:
    raise RuntimeError("Missing Telegram credentials in .env")

client = TelegramClient(
    str(BASE_DIR / "tg_manager_readonly"),
    api_id,
    api_hash
)

channels = []
total_dialogs = 0

try:
    client.start()

    print("\nConnected. Scanning ALL accessible dialogs...")
    print("This may take a little time.\n")

    for dialog in client.iter_dialogs():
        total_dialogs += 1
        entity = dialog.entity

        if not isinstance(entity, Channel):
            continue

        title = entity.title or dialog.name
        username = entity.username or ""

        if entity.broadcast:
            channel_type = "Broadcast Channel"
        elif entity.megagroup:
            channel_type = "Supergroup"
        else:
            channel_type = "Other Channel"

        channels.append({
            "title": title,
            "username": f"@{username}" if username else "",
            "id": entity.id,
            "type": channel_type
        })

    with open(
        CSV_FILE,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["title", "username", "id", "type"]
        )
        writer.writeheader()
        writer.writerows(channels)

    print("=" * 55)
    print("SCAN COMPLETE")
    print("=" * 55)
    print(f"Total dialogs scanned : {total_dialogs}")
    print(f"Channel entries found : {len(channels)}")
    print(f"Public usernames      : {sum(bool(c['username']) for c in channels)}")
    print(f"Private/no username   : {sum(not c['username'] for c in channels)}")
    print(f"\nInventory saved to:\n{CSV_FILE}")

    print("\nFirst 10 channel titles:")
    for channel in channels[:10]:
        print(f"- {channel['title']} ({channel['id']})")

except Exception as error:
    print(f"\nError: {type(error).__name__}: {error}")

finally:
    client.disconnect()
