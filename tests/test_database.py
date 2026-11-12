"""
Unit tests for LevitorBot SQLite database operations.
Uses an isolated temporary database to verify schema migrations and CRUD operations.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database as db


class TestDatabaseOperations(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_levitor.db"
        self.patcher = patch("database.DB_PATH", self.db_path)
        self.patcher.start()
        db.ensure_schema()

    def tearDown(self):
        self.patcher.stop()
        self.temp_dir.cleanup()

    def test_schema_and_default_categories(self):
        """Verify tables are created and default categories seeded."""
        cats = db.get_categories()
        self.assertGreater(len(cats), 0)
        names = [c["name"] for c in cats]
        self.assertIn("Direct Content", names)
        self.assertIn("Link Sharing", names)

    def test_settings_storage(self):
        """Verify setting key/value pairs in app_metadata."""
        self.assertIsNone(db.get_setting("non_existent_key"))
        self.assertEqual(db.get_setting("non_existent_key", default="fallback"), "fallback")

        db.set_setting("terabox_cookie", "test_ndus_token_12345")
        self.assertEqual(db.get_setting("terabox_cookie"), "test_ndus_token_12345")

        # Update existing
        db.set_setting("terabox_cookie", "updated_ndus_token_67890")
        self.assertEqual(db.get_setting("terabox_cookie"), "updated_ndus_token_67890")

    def test_category_crud(self):
        """Verify creating, renaming, and deleting categories."""
        cid = db.create_category("Test Shelf")
        self.assertIsNotNone(cid)
        cat = db.get_category(cid)
        self.assertEqual(cat["name"], "Test Shelf")

        db.rename_category(cid, "Renamed Shelf")
        cat = db.get_category(cid)
        self.assertEqual(cat["name"], "Renamed Shelf")

        db.delete_category(cid)
        self.assertIsNone(db.get_category(cid))

    def test_channel_sync_and_retrieval(self):
        """Verify importing dialogs and reading channel records."""
        sample_dialogs = [
            {
                "id": "1001",
                "title": "Alpha News Channel",
                "username": "alphanews",
                "type": "Broadcast Channel",
            },
            {
                "id": "1002",
                "title": "Beta Community Chat",
                "username": "",
                "type": "Supergroup",
            },
        ]
        res = db.save_sync_results(sample_dialogs, "2026-11-12T00:00:00Z")
        self.assertEqual(res["seen"], 2)
        self.assertEqual(res["added"], 2)
        self.assertEqual(db.get_total_channel_count(), 2)

        ch = db.get_channel("1001")
        self.assertIsNotNone(ch)
        self.assertEqual(ch["title"], "Alpha News Channel")
        self.assertEqual(ch["username"], "alphanews")

    def test_channel_search(self):
        """Verify searching channels by title and username."""
        sample = [
            {"id": "2001", "title": "Technology Daily", "username": "techdaily", "type": "Broadcast Channel"},
            {"id": "2002", "title": "Crypto Updates", "username": "cryptonews", "type": "Broadcast Channel"},
        ]
        db.save_sync_results(sample, "2026-11-12T00:00:00Z")

        results = db.search_channels("Daily")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "2001")

        results = db.search_channels("cryptonews")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "2002")

    def test_channel_category_assignment(self):
        """Verify toggling category assignments on channels."""
        sample = [{"id": "3001", "title": "Science Hub", "username": "", "type": "Broadcast Channel"}]
        db.save_sync_results(sample, "2026-11-12T00:00:00Z")

        cats = db.get_categories()
        first_cat_id = cats[0]["category_id"]

        # Assign
        assigned = db.toggle_channel_category("3001", first_cat_id)
        self.assertTrue(assigned)
        assigned_ids = [r["category_id"] for r in db.get_channel_categories("3001")]
        self.assertIn(first_cat_id, assigned_ids)

        # Unassign (toggle off)
        assigned = db.toggle_channel_category("3001", first_cat_id)
        self.assertFalse(assigned)
        assigned_ids = [r["category_id"] for r in db.get_channel_categories("3001")]
        self.assertNotIn(first_cat_id, assigned_ids)


if __name__ == "__main__":
    unittest.main()
