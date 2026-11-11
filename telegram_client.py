"""
Telethon MTProto Client Operations and Channel Link Resolvers.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, Optional

from telethon import TelegramClient
from telethon.tl import types
from telethon.tl.types import PeerChannel

from config import SESSION_PATH, API_ID, API_HASH
from database import save_sync_results

logger = logging.getLogger(__name__)


def create_telethon_client() -> TelegramClient:
    """Create a Telethon user client instance."""
    return TelegramClient(
        SESSION_PATH,
        int(API_ID),
        API_HASH,
    )


async def sync_main_dialogs(client: TelegramClient) -> Dict[str, int]:
    """Import only channels/groups in the main chat list (folder 0); never DMs or bots."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    discovered = []

    # Telethon folder=0 means the main chat list; archived folder=1 is excluded.
    async for dialog in client.iter_dialogs(folder=0):
        entity = dialog.entity

        if isinstance(entity, types.Channel):
            kind = "Broadcast Channel" if getattr(entity, "broadcast", False) else "Supergroup"
        elif isinstance(entity, types.Chat):
            kind = "Basic Group"
        else:
            # Exclude direct chats, bot dialogs, and non-channel entities
            continue

        discovered.append({
            "id": str(entity.id),
            "title": (getattr(entity, "title", None) or "Untitled").strip(),
            "username": (getattr(entity, "username", None) or "").strip(),
            "type": kind,
        })

    return save_sync_results(discovered, now)


async def resolve_channel_link(client: TelegramClient, channel: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """
    Resolve a clickable opening link for a channel.
    Returns (url, error_message).
    """
    username = (channel["username"] or "").strip().lstrip("@")
    if username:
        return f"https://t.me/{username}", None

    if channel["type"] == "Basic Group":
        return None, "This is a basic group. Open it from your Telegram chat list."

    try:
        channel_id = int(channel["id"])
        peer = await client.get_input_entity(PeerChannel(channel_id))
        messages = await client.get_messages(peer, limit=1)

        if not messages or not messages[0].id:
            return None, "This destination has no available message link yet."

        return f"https://t.me/c/{channel_id}/{messages[0].id}", None
    except Exception as exc:
        logger.exception("Could not resolve private channel link: %s", exc)
        return None, "Could not generate an opening link. Check account access."
