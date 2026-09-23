from __future__ import annotations

from backend.extensions import db


class Procurement(db.Model):
    """Государственная закупка."""
    __tablename__ = "procurements"

    id = db.Column(db.Integer, primary_key=True)
    procurement_number = db.Column(
        db.String(64), unique=True, nullable=False, index=True
    )
    title = db.Column(db.Text, nullable=False)
    okpd2_code = db.Column(db.String(32), nullable=False, index=True)
    okpd2_name = db.Column(db.Text)
    region = db.Column(db.String(128), nullable=False)
    initial_price = db.Column(db.Numeric(15, 2), nullable=False)
    keywords = db.Column(db.Text)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    matches = db.relationship(
        "MatchingResult",
        back_populates="procurement",
        cascade="all, delete-orphan",
    )

    def to_dict(self) -> dict:
        """Сериализует закупку для клиента."""
        return {
            "procurement_id": self.procurement_number,
            "title": self.title,
            "okpd2": self.okpd2_code,
            "okpd2_name": self.okpd2_name,
            "region": self.region,
            "initial_price": float(self.initial_price),
            "keywords": self.keywords,
        }