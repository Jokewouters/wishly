#!/bin/sh
set -eu
node --check docs/app.js
node --check docs/config.js
python3 - <<'PYTEST'
from pathlib import Path
s=Path('supabase/schema.sql').read_text()
for tok in ['enable row level security','revoke all on table','wishly_reservations','wishly_public_items','wishly_reserve']:
 assert tok in s, tok
for p in ['docs/index.html','docs/app.js','docs/style.css','docs/config.js','.github/workflows/pages.yml']:
 assert Path(p).is_file(), p
print('Static/smoke checks passed; Supabase integration not tested.')
PYTEST
