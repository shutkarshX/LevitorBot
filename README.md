# Snapit (TG-Manager)

A private Telegram space and destination manager bot. **Snapit** pairs a **Telegram Bot** interface with a **Telethon user client** to inspect, organize, search, categorize, and safely back up your Telegram channels and supergroups.

---

## ✨ Features

- **Strict Whitelist & Privacy**: Only your own Telegram account (whitelisted via your Telethon user ID) can access and interact with the bot in private messages. All others receive an access-denied alert.
- **Main Chat-List Synchronization**:
  - Scans active channels and supergroups from your primary chat list (`folder=0`).
  - Ignores DMs, bots, and archived conversations.
  - Automatically identifies new channels and queues them for categorization.
  - Fail-closed reconciliation: ensures channels no longer in your list are cleaned up safely without risking data loss.
- **Multi-Category Shelving**:
  - Assign channels to multiple custom categories/shelves with single-tap toggle buttons.
  - Dedicated **🆕 Newly Added** review queue and **📭 Uncategorised** list.
  - Pagination (8 items per page) for channels and categories.
- **Direct Telegram Opener**:
  - Direct links to public `@username` channels.
  - Dynamically fetches the latest message ID via MTProto to generate deep links (`t.me/c/<id>/<msg_id>`) for private channels and supergroups.
- **Live Database Snapshots in Chat**:
  - Built-in `/menu` -> Management -> Download backup.
  - Uses SQLite's online backup API to take a point-in-time snapshot, runs `PRAGMA integrity_check`, and sends the `.db` file directly to you inside Telegram.
- **TeraBox Watch & Download Engine**:
  - Send **any TeraBox share link** directly to the bot.
  - Instant metadata resolution (title and file size).
  - One-tap buttons for **▶️ Watch Online** and **⬇️ Fast Download** (bypassing TeraBox's heavy ads, app install prompts, and redirect loops).
  - Ad-free companion bridge via **iTeraPlay** (`iteraplay.com`).
  - Supports optional API keys (`TERABOX_API_KEY`) or personal cookies (`TERABOX_COOKIE`) for direct in-chat download links.
- **Zero-Config Database Initialization**:
  - The bot automatically creates the SQLite database, tables, indexes, and default categories if starting fresh.

---

## 📂 Project Structure

```text
├── main.py                    # Root entry point (universal hosting panel compatibility)
├── tg_manager_bot.py          # Bot bootstrap & application runner
├── config.py                  # Environment config and project constants
├── database.py                # SQLite schema auto-setup, migrations, and queries
├── telegram_client.py         # Telethon client session, sync, and link generator
├── ui.py                      # Menus, keyboards, layouts, and admin access control
├── handlers.py                # Command, callback, message, and backup handlers
├── terabox.py                 # TeraBox link detection, extraction, and player bridge
├── login_session.py           # Helper script to authenticate Telethon session locally
├── requirements.txt           # Python dependencies
├── .env.example               # Example environment variable configuration
├── .gitignore                 # Ignores sessions, databases, and local caches
├── scripts/
│   ├── backup_database.py     # Standalone SQLite database backup utility
│   ├── migrate_archive.py     # Migration tool for legacy CSV archives
│   └── prepare_sync_review.py # Diagnostic script for pre-sync reviews
└── data/                      # Auto-created at runtime: stores tg_manager.db
```

---

## 🚀 Setup & Local Quickstart

### 1. Prerequisites
- Python 3.10+
- Telegram Bot Token from [@BotFather](https://t.me/BotFather)
- Telegram `API_ID` and `API_HASH` from [my.telegram.org](https://my.telegram.org)

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment
Create a `.env` file from the example template:
```bash
cp .env.example .env
```
Fill in your credentials:
```env
BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
TG_API_ID=12345678
TG_API_HASH=0123456789abcdef0123456789abcdef
```

### 4. Generate Telethon Session
Because Telegram sends a one-time login code (and requires your 2FA password if enabled), authenticate the user session on your local machine first:
```bash
python login_session.py
```
This generates `tg_manager_readonly.session` in the root directory.

### 5. Run the Bot
```bash
python tg_manager_bot.py
```
Open Telegram, message your bot, and send `/start`.

---

## ☁️ Deploying to SillyDev / Pterodactyl Panel (`sillydev.co.uk/panel`)

Pterodactyl panel environments run in headless Docker containers and cannot accept interactive terminal inputs (such as phone numbers and 2FA SMS codes). Follow these steps to deploy seamlessly:

### Step 1: Prepare Files Locally
1. Ensure your `.env` contains your correct `BOT_TOKEN`, `TG_API_ID`, and `TG_API_HASH`.
2. Run `python login_session.py` on your computer to create `tg_manager_readonly.session`.

### Step 2: Upload Files to the Panel
In the SillyDev file manager:
1. Clone or upload the repository files.
2. Upload your `.env` file.
3. Upload `tg_manager_readonly.session` to the root folder.
4. *(Optional)* If you already have existing channel data, upload your `data/tg_manager.db`. If you don't, the bot will automatically initialize a fresh database on first boot.

### Step 3: Configure Startup Command
In your SillyDev server's **Startup** settings:
- Ensure the startup command executes:
  ```bash
  python tg_manager_bot.py
  ```
  *(or `python3 tg_manager_bot.py` depending on the container egg configuration)*.

### Step 4: Start the Server
Start the server in the panel console. You should see:
```text
Snapit administrator identity loaded.
Bot startup initialization complete.
Starting Snapit bot polling.
```

---

## 🔒 Security & Safe Operation

- Never commit `.env`, `*.session`, or `*.db` files to public version control. They are protected by `.gitignore`.
- Telethon sessions have full access to your Telegram account. Keep `tg_manager_readonly.session` secure.
- Synchronization deliberately excludes direct messages (DMs), bot conversations, and archived dialogs to preserve privacy.
