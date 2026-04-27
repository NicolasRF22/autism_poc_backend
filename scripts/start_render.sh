#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$BACKEND_DIR"

if [ -n "${DATABASE_URL:-}" ]; then
  echo "[start] sincronizando dados locais no Supabase/PostgreSQL"
  python3 "$BACKEND_DIR/scripts/sync_supabase_from_files.py"
else
  echo "[start] DATABASE_URL ausente; pulando sincronização"
fi

exec gunicorn app:app --bind 0.0.0.0:${PORT:-5000} --workers 1 --threads 4 --timeout 120
