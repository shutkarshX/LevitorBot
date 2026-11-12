# LevitorBot — Telegram Content & Media Automation Bot

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![python-telegram-bot](https://img.shields.io/badge/Telegram%20Bot-v22.8-2CA5E0.svg)](https://python-telegram-bot.org/)
[![Telethon](https://img.shields.io/badge/Telethon-v1.45-388E3C.svg)](https://github.com/LonamiWebs/Telethon)
[![SQLite](https://img.shields.io/badge/Database-SQLite-003B57.svg)](https://www.sqlite.org/)
[![Tests](https://img.shields.io/badge/Tests-20%2F20%20Passed-brightgreen.svg)]()
[![CI](https://img.shields.io/badge/CI-GitHub%20Actions-success.svg)](.github/workflows/python-tests.yml)

An asynchronous Telegram automation and media management bot built using **python-telegram-bot**, **Telethon**, and **SQLite**. It features high-speed media resolution, multi-tier TeraBox link extraction with direct download/stream generation, channel administration workflows, and persistent user configuration.

---

## 🏛️ System & Link Resolution Architecture

```mermaid
graph TD
    User([Telegram User]) -->|"Sends Message / Link"| BotCore["Telegram Bot Core<br/>(tg_manager_bot.py)"]
    
    BotCore --> MsgFilter{"Message Type"}
    
    MsgFilter -->|"Standard Command"| CmdHandler["Command Router<br/>(/start, /help, /terabox)"]
    MsgFilter -->|"TeraBox Share Link"| ResolverEngine["TeraBox Resolver Engine<br/>(terabox_resolvers.py)"]

    ResolverEngine --> PrefCheck{"Check User Mode in SQLite<br/>(data/levitor.db)"}

    PrefCheck -->|"External API"| ExtScraper["TeraBoxDL API Gateway<br/>(Fast HTTPS Extraction)"]
    PrefCheck -->|"Native Scraper"| NativeScraper["Built-in Public Scraper<br/>(Direct Web Traversal)"]
    PrefCheck -->|"Cookie Assisted"| CookieScraper["ndus Session Resolver<br/>(High-Fidelity Extraction)"]

    ExtScraper & NativeScraper & CookieScraper --> URLValidator{"Direct Media URL Extracted?"}
    
    URLValidator -->|"Success"| ActionButtons["Build Telegram Inline Buttons<br/>[▶️ Stream Video] [⬇️ Direct Download]"]
    URLValidator -->|"Fallback"| Fallback["Prompt User Method Switch (/terabox)"]

    ActionButtons --> User
```

---

## ⚡ Core Features

1. **Multi-Provider Link Extraction:**
   * **Hosted API Gateway (`TeraBoxDL`)**: High-speed cloud-based extraction using API tokens.
   * **Native Scraper**: In-house DOM and metadata parser for public share links.
   * **Cookie-Assisted Scraper**: Advanced session-cookie (`ndus`) resolver for protected files.
2. **User Preference Customization:**
   * Telegram users select their preferred resolver route via the `/terabox` command, securely remembered across sessions in SQLite.
3. **Streamlined Inline UI:**
   * Delivers direct streaming playback buttons and high-speed browser download links straight inside the chat.
4. **Dual Engine (Bot API + Userbot Client):**
   * Combines official `python-telegram-bot` event handling with `Telethon` for extended media indexing and message routing.

---

## 🧪 Automated Test Suite (20 Tests)

All URL parsers, resolver fallback chains, response normalization routines, and database operations are covered by Pytest:

```bash
python -m pytest tests/
```

```text
============================= test session starts =============================
platform win32 -- Python 3.14.7, pytest-9.1.1
collected 20 items

tests/test_terabox.py ........                                           [ 40%]
tests/test_terabox_resolvers.py ............                             [100%]

============================= 20 passed in 0.32s ==============================
```

---

## 🚀 Setup & Deployment

### Prerequisites
* **Python**: 3.10 or newer
* Telegram Bot API Token from [@BotFather](https://t.me/BotFather)
* Telegram API ID & Hash from [my.telegram.org](https://my.telegram.org) (for Telethon userbot features)

### 1. Install Dependencies
```bash
git clone https://github.com/shutkarshX/LevitorBot.git
cd LevitorBot
pip install -r requirements.txt
```

### 2. Environment Configuration
Create a `.env` file in the root directory:

```dotenv
BOT_TOKEN=your_telegram_bot_token
API_ID=your_telegram_api_id
API_HASH=your_telegram_api_hash

# TeraBox Resolver Keys (Optional)
TERABOX_API_KEY=your_teraboxdl_api_key
TERABOX_EXTERNAL_RESOLVER_URL=
TERABOX_NDUS_COOKIE=
```

### 3. Run the Bot
```bash
python tg_manager_bot.py
```

---

## 📂 Repository Structure

```text
LevitorBot/
├── tg_manager_bot.py          # Primary asynchronous Telegram bot application
├── terabox.py                 # Core link extraction and button generator
├── terabox_resolvers.py       # Multi-provider resolution handlers
├── tests/                     # 20 automated Pytest test cases
│   ├── test_terabox.py
│   └── test_terabox_resolvers.py
├── scripts/                   # Database migration & backup utilities
├── data/                      # Persistent SQLite storage (levitor.db)
├── docs/                      # Technical resolver documentation
├── .github/workflows/         # CI/CD automated test pipeline
├── requirements.txt
└── README.md
```
