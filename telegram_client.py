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
    """
    Create a Telethon user client instance in lightweight read-only mode.
    Disables incoming account updates to prevent memory leaks and console log spam.
    """
    return TelegramClient(
        SESSION_PATH,
        int(API_ID),
        API_HASH,
        receive_updates=False,
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
        channel_id = int(channel["id"])
        # 1. Try to fetch existing exported invite link if present
        try:
            from telethon.tl.functions.messages import GetFullChatRequest
            full_res = await client(GetFullChatRequest(chat_id=channel_id))
            full = getattr(full_res, "full_chat", None)
            exported = getattr(full, "exported_invite", None)
            if exported and hasattr(exported, "link") and exported.link:
                return exported.link, None
        except Exception as exc:
            logger.debug("Could not query exported invite for basic group %s: %s", channel_id, exc)

        # 2. Native Telegram deep-link for the member to open in app directly
        return f"tg://openmessage?chat_id={channel_id}", None

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
