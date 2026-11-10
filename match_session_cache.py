import sqlite3
from pathlib import Path
from telethon.utils import resolve_id
from telethon.tl.types import PeerChannel

archive = sqlite3.connect("data/tg_manager.db")
session_path = Path("tg_manager_readonly.session")

session = sqlite3.connect(
    f"file:{session_path.resolve().as_posix()}?mode=ro",
    uri=True
)

channels = {
    str(row[0]).strip(): str(row[1] or "").strip()
    for row in archive.execute("SELECT id, username FROM channels")
}

cached = {}

for marked_id, access_hash, username, phone, name, date in session.execute(
    "SELECT id, hash, username, phone, name, date FROM entities"
):
    raw_id, peer_type = resolve_id(marked_id)

    if peer_type is PeerChannel:
        cached[str(raw_id)] = {
            "username": (username or "").strip(),
            "has_hash": access_hash is not None
        }

matched = set(channels) & set(cached)

existing_usernames = sum(bool(channels[i]) for i in matched)
recoverable_usernames = sum(
    not channels[i] and bool(cached[i]["username"])
    for i in matched
)
with_hash = sum(cached[i]["has_hash"] for i in matched)

print("=== ARCHIVE / SESSION MATCH ===")
print("Archived channels:", len(channels))
print("Matching cached channels:", len(matched))
print("Not found in cache:", len(channels) - len(matched))
print("Matching records with access hash:", with_hash)

print("\n=== USERNAME RECOVERY ===")
print("Already had username:", existing_usernames)
print("Potentially recoverable usernames:", recoverable_usernames)
print("Still without cached username:", len(matched) - existing_usernames - recoverable_usernames)

session.close()
archive.close()
