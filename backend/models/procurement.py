from __future__ import annotations

from datetime import datetime

from backend.extensions import db


class Procurement(db.Model):
    """Заявка заказчика или импортированный закупочный контекст."""
    __tablename__ = "procurements"

    id = db.Column(db.Integer, primary_key=True)
    procurement_number = db.Column(db.String(64), unique=True, nullable=False, index=True)
    title = db.Column(db.Text, nullable=False)
    subject = db.Column(db.Text)
    okpd2_code = db.Column(db.String(32), nullable=True, index=True)
    okpd2_name = db.Column(db.Text)
    region = db.Column(db.String(128), nullable=False, default="Санкт-Петербург")
    delivery_region = db.Column(db.String(128), nullable=False, default="Санкт-Петербург")
    initial_price = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    keywords = db.Column(db.Text)

    customer_inn = db.Column(db.String(12), index=True)
    customer_kpp = db.Column(db.String(12))
    source_system = db.Column(db.String(32))  # USER / АИС ГЗ / ЭМ / DEMO
    is_smp = db.Column(db.Boolean)
    procurement_kind = db.Column(db.String(16))  # goods / services / works
    input_mode = db.Column(db.String(16), default="manual")  # manual / spec
    publish_date = db.Column(db.Date)

    # Выбор всегда делает заказчик, алгоритм только рекомендует.
    selected_supplier_inn = db.Column(db.String(12))
    selected_at = db.Column(db.DateTime)

    # Жизненный цикл пользовательской заявки.
    status = db.Column(db.String(24), nullable=False, default="matching", index=True)
    completed_at = db.Column(db.DateTime)
    archived_at = db.Column(db.DateTime)
    deleted_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    matches = db.relationship(
        "MatchingResult",
        back_populates="procurement",
        cascade="all, delete-orphan",
    )
    reviews = db.relationship(
        "SupplierReview",
        back_populates="procurement",
        cascade="all, delete-orphan",
    )

    @property
    def is_user_request(self) -> bool:
        return (self.source_system or "").upper() == "USER"

    def to_dict(self) -> dict:
        return {
            "procurement_id": self.procurement_number,
            "title": self.title,
            "subject": self.subject,
            "okpd2": self.okpd2_code or "",
            "okpd2_name": self.okpd2_name,
            "region": self.region,
            "delivery_region": self.delivery_region or self.region,
            "initial_price": float(self.initial_price or 0),
            "keywords": self.keywords,
            "customer_inn": self.customer_inn,
            "source_system": self.source_system,
            "is_smp": self.is_smp,
            "procurement_kind": self.procurement_kind,
            "input_mode": self.input_mode,
            "status": self.status,
            "selected_supplier_inn": self.selected_supplier_inn,
        }
