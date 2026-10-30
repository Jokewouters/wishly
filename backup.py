#!/usr/bin/env python3
"""Consistent SQLite snapshot. Invoke from project root, on the HOST."""
from pathlib import Path
import os, sqlite3, datetime
base = Path(__file__).resolve().parent
src = base / 'data' / 'wishly.sqlite3'
if not src.exists(): raise SystemExit(f'Database not found: {src}')
folder = base / 'backups'
folder.mkdir(parents=True, exist_ok=True, mode=0o700)
folder.chmod(0o700)
name = datetime.datetime.now(datetime.timezone.utc).strftime('wishly-%Y%m%dT%H%M%SZ.sqlite3')
out = folder / name
with sqlite3.connect(f'file:{src}?mode=ro', uri=True) as source, sqlite3.connect(out) as destination:
    source.backup(destination)
    check = destination.execute('PRAGMA integrity_check').fetchone()[0]
    if check != 'ok': raise RuntimeError('Integrity check failed: ' + check)
os.chmod(out, 0o600)
print('Created', out)
