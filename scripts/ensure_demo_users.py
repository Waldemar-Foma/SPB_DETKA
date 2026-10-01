from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import create_app
from backend.services.demo_users import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    DEMO_PASSWORD,
    ensure_admin_user,
    ensure_demo_users,
)

ap = argparse.ArgumentParser()
ap.add_argument("--admin-only", action="store_true", help="Создать только локального администратора, без demo-заказчика")
args = ap.parse_args()

app = create_app("dev")
with app.app_context():
    if args.admin_only:
        count = ensure_admin_user()
        print(f"Администратор готов. Создано новых: {count}")
        print(f"Логин: {ADMIN_EMAIL}; пароль: {ADMIN_PASSWORD}")
    else:
        count = ensure_demo_users()
        print(f"Demo-заказчик готов. Создано новых аккаунтов: {count}")
        print(f"customer@demo.local / {DEMO_PASSWORD}")
        print(f"Администратор: {ADMIN_EMAIL}; пароль: {ADMIN_PASSWORD}")
