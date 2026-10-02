#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then
  (umask 077; python3 - <<'PY'
import secrets
from pathlib import Path
Path('.env').write_text('POSTGRES_PASSWORD=' + secrets.token_urlsafe(32) + '\nAPI_PORT=8000\n')
PY
  )
fi
docker compose up --build -d --wait
printf '\nLocal synthetic API: http://localhost:8000/docs (or API_PORT from .env)\n'
