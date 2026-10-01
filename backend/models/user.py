from __future__ import annotations

from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

from backend.extensions import db


ROLE_LABELS = {
    "customer": "Заказчик",
    "admin": "Администратор",
}


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(255), nullable=False)
    account_role = db.Column(db.String(32), nullable=False, default="customer", index=True)
    organization_inn = db.Column(db.String(12), nullable=False, index=True)
    organization_name = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_login_at = db.Column(db.DateTime)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def role_label(self) -> str:
        return ROLE_LABELS.get(self.account_role, self.account_role)

    @property
    def initials(self) -> str:
        words = [w for w in (self.full_name or "").strip().split() if w]
        if not words:
            return "ЗК"
        return "".join(w[0].upper() for w in words[:2])


class RegistrySync(db.Model):
    """Журнал офлайн-обогащения реестрами, видимый в интерфейсе."""

    __tablename__ = "registry_syncs"

    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(64), nullable=False, index=True)
    status = db.Column(db.String(32), nullable=False, default="ok")
    rows_total = db.Column(db.Integer, default=0, nullable=False)
    matched_suppliers = db.Column(db.Integer, default=0, nullable=False)
    file_path = db.Column(db.String(512))
    message = db.Column(db.Text)
    finished_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
