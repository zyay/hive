#!/usr/bin/env python3
"""
Hive Backup & Restore — Backup all data to a timestamped archive.
Usage: python backup.py [backup|restore] [archive_path]
"""

import sys
import shutil
import tarfile
import datetime
from pathlib import Path

BACKUP_DIR = Path("backups")
DATA_DIRS = ["keystore", "hive_memory", "uploads", "skills", "relay_mailbox", "workspace_files"]
DATA_FILES = ["hive.db", "hive_secret.key", "hive_apikeys.db", "hive_memory.db", "hive_scheduler.db"]


def backup(output_path: str = None):
    """Create a backup archive of all Hive data."""
    BACKUP_DIR.mkdir(exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    if not output_path:
        output_path = str(BACKUP_DIR / f"hive_backup_{timestamp}.tar.gz")
    
    print(f"Creating backup: {output_path}")
    
    with tarfile.open(output_path, "w:gz") as tar:
        for dir_name in DATA_DIRS:
            dir_path = Path(dir_name)
            if dir_path.exists():
                print(f"  Adding directory: {dir_name}")
                tar.add(dir_name, arcname=dir_name)
        
        for file_name in DATA_FILES:
            file_path = Path(file_name)
            if file_path.exists():
                print(f"  Adding file: {file_name}")
                tar.add(file_name, arcname=file_name)
    
    size_mb = Path(output_path).stat().st_size / (1024 * 1024)
    print(f"\nBackup complete: {output_path} ({size_mb:.2f} MB)")


def restore(archive_path: str):
    """Restore Hive data from a backup archive."""
    if not Path(archive_path).exists():
        print(f"Error: Archive not found: {archive_path}")
        sys.exit(1)
    
    print(f"Restoring from: {archive_path}")
    print("WARNING: This will overwrite existing data!")
    
    confirm = input("Continue? (yes/no): ")
    if confirm.lower() != "yes":
        print("Aborted.")
        return
    
    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extractall(".")
    
    print("Restore complete. Restart Hive to apply changes.")


def list_backups():
    """List all available backups."""
    if not BACKUP_DIR.exists():
        print("No backups found.")
        return
    
    backups = sorted(BACKUP_DIR.glob("*.tar.gz"), reverse=True)
    if not backups:
        print("No backups found.")
        return
    
    print(f"Available backups ({len(backups)}):\n")
    for b in backups:
        size_mb = b.stat().st_size / (1024 * 1024)
        mtime = datetime.datetime.fromtimestamp(b.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"  {b.name:40s} {size_mb:8.2f} MB  {mtime}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python backup.py [backup|restore|list] [archive_path]")
        print("\nCommands:")
        print("  backup [path]   Create a new backup archive")
        print("  restore <path>  Restore from a backup archive")
        print("  list            List all available backups")
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "backup":
        path = sys.argv[2] if len(sys.argv) > 2 else None
        backup(path)
    elif cmd == "restore":
        if len(sys.argv) < 3:
            print("Error: Specify archive path")
            sys.exit(1)
        restore(sys.argv[2])
    elif cmd == "list":
        list_backups()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
