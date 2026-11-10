import sqlite3
from pathlib import Path

source = sqlite3.connect("data/tg_manager.db")
target = sqlite3.connect(r"D:\ME\Projects\TG-Manager\backups\pre_sync_20261110_234031\tg_manager.db")

source.backup(target)

target.close()
source.close()
print("Database backup completed.")
