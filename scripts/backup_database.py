import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "tg_manager.db"
BACKUP_DIR = ROOT / "backups"

if not DB_PATH.is_file():
    raise SystemExit(f"Database not found at: {DB_PATH}")

BACKUP_DIR.mkdir(parents=True, exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
target_path = BACKUP_DIR / f"tg_manager_backup_{timestamp}.db"

source = sqlite3.connect(DB_PATH)
target = sqlite3.connect(target_path)

source.backup(target)

target.close()
source.close()
print(f"Database backup completed successfully: {target_path}")
