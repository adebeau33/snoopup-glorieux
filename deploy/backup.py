#!/usr/bin/env python3
"""Root-only consistent SQLite snapshot, seven daily copies on the same host."""
from pathlib import Path
import sqlite3,datetime,os
os.umask(0o077)
root=Path('/var/backups/glorieux');root.mkdir(mode=0o700,parents=True,exist_ok=True)
path=root/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')+'.sqlite3')
with sqlite3.connect('file:/var/lib/glorieux/db.sqlite3?mode=ro',uri=True) as source:
 with sqlite3.connect(path) as destination:source.backup(destination)
for old in sorted(root.glob('*.sqlite3'),reverse=True)[7:]:old.unlink()
print('Sauvegarde cohérente Glorieux créée ; sept copies locales conservées.')
