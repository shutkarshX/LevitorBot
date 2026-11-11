"""
Unit tests for Telegram channel and group opening link resolution.
"""
import unittest
from unittest.mock import AsyncMock, MagicMock
from telegram_client import resolve_channel_link


class TestTelegramClientLinkResolution(unittest.IsolatedAsyncioTestCase):
    async def test_public_username_resolution(self):
        """Channels with usernames resolve to public t.me/username links."""
        channel = {"id": "123", "title": "Public Channel", "username": "@mychannel", "type": "Broadcast Channel"}
        mock_client = AsyncMock()
        url, err = await resolve_channel_link(mock_client, channel)
        self.assertIsNone(err)
        self.assertEqual(url, "https://t.me/mychannel")

    async def test_basic_group_exported_invite(self):
        """Basic groups with an existing exported invite return the invite link."""
        channel = {"id": "555", "title": "My Basic Group", "username": "", "type": "Basic Group"}
        mock_client = AsyncMock()

        # Mock full chat response with exported invite
        mock_res = MagicMock()
        mock_res.full_chat.exported_invite.link = "https://t.me/+joinhash123"
        mock_client.return_value = mock_res

        url, err = await resolve_channel_link(mock_client, channel)
        self.assertIsNone(err)
        self.assertEqual(url, "https://t.me/+joinhash123")

    async def test_basic_group_deep_link_fallback(self):
        """Basic groups without an exported invite return native tg:// deep-link."""
        channel = {"id": "777", "title": "Private Basic Group", "username": "", "type": "Basic Group"}
        mock_client = AsyncMock()
        mock_client.side_effect = Exception("No exported invite")

        url, err = await resolve_channel_link(mock_client, channel)
        self.assertIsNone(err)
        self.assertEqual(url, "tg://openmessage?chat_id=777")

    async def test_private_channel_message_link(self):
        """Private supergroups/channels resolve to t.me/c/<id>/<msg_id> format."""
        channel = {"id": "999", "title": "Private Supergroup", "username": "", "type": "Supergroup"}
        mock_client = AsyncMock()
        mock_msg = MagicMock()
        mock_msg.id = 42
        mock_client.get_messages.return_value = [mock_msg]

        url, err = await resolve_channel_link(mock_client, channel)
        self.assertIsNone(err)
        self.assertEqual(url, "https://t.me/c/999/42")


if __name__ == "__main__":
    unittest.main()
