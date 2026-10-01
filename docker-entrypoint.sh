#!/bin/sh
set -eu

cd /app
mkdir -p /app/instance /app/data /datasets

DATASET="${DATASET_PATH:-/datasets/source.zip}"
REAL_MARKER="/app/instance/REAL_DATA_READY"
DB_FILE="/app/instance/app_dev.db"

if [ -f "$REAL_MARKER" ]; then
  echo "[startup] REAL база уже подготовлена."
  python scripts/ensure_demo_users.py --admin-only
elif [ -f "$DATASET" ]; then
  echo "[startup] Найден реальный датасет: $DATASET"
  echo "[startup] Первый импорт блокирует только контейнер app; прогресс печатается сюда."
  python scripts/build_real_db.py --dataset "$DATASET" --procurement-limit "${PROCUREMENT_LIMIT:-1500}" --contracts-per-supplier "${CONTRACTS_PER_SUPPLIER:-50}"
  printf '%s\n' "$DATASET" > "$REAL_MARKER"
  python scripts/ensure_demo_users.py --admin-only
else
  echo "[startup] Реальный датасет не найден. Запускаю DEMO."
  if [ ! -f "$DB_FILE" ]; then
    python seed.py
  fi
  python scripts/ensure_demo_users.py
fi

exec python app.py
