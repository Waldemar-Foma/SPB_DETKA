from __future__ import annotations

from datetime import datetime

from backend.extensions import db


class SupplierReview(db.Model):
    __tablename__ = "supplier_reviews"
    __table_args__ = (
        db.UniqueConstraint("procurement_id", "user_id", name="uq_review_request_user"),
    )

    id = db.Column(db.Integer, primary_key=True)
    procurement_id = db.Column(db.Integer, db.ForeignKey("procurements.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    rating = db.Column(db.Integer, nullable=False)
    quality_rating = db.Column(db.Integer)
    deadlines_rating = db.Column(db.Integer)
    communication_rating = db.Column(db.Integer)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    procurement = db.relationship("Procurement", back_populates="reviews")
    supplier = db.relationship("Supplier", back_populates="reviews")
    user = db.relationship("User")


class ExternalMention(db.Model):
    """Кэш реальных внешних упоминаний, найденных через публичный веб-поиск.

    Мы не превращаем сниппеты поиска в выдуманный рейтинг: сохраняем только
    источник, ссылку, заголовок и текст сниппета, чтобы заказчик мог открыть
    первоисточник.
    """

    __tablename__ = "external_mentions"
    __table_args__ = (
        db.UniqueConstraint("supplier_id", "url", name="uq_external_mention_url"),
    )

    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True)
    source = db.Column(db.String(64), nullable=False, default="web")
    title = db.Column(db.String(500))
    url = db.Column(db.String(1500), nullable=False)
    snippet = db.Column(db.Text)
    found_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    supplier = db.relationship("Supplier", back_populates="external_mentions")
