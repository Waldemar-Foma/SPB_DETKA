from backend.extensions import db


class MatchingResult(db.Model):
    """Опциональный кэш результатов сопоставления."""
    __tablename__ = "matching_results"
    __table_args__ = (
        db.UniqueConstraint("procurement_id", "supplier_id", name="uq_match_pair"),
    )

    id = db.Column(db.Integer, primary_key=True)
    procurement_id = db.Column(db.Integer, db.ForeignKey("procurements.id", ondelete="CASCADE"), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False)
    total_score = db.Column(db.Integer, nullable=False)
    okpd2_score = db.Column(db.Integer, nullable=False)
    product_score = db.Column(db.Integer, nullable=False)
    experience_score = db.Column(db.Integer, nullable=False)
    customer_score = db.Column(db.Integer, nullable=False, default=0)
    role_score = db.Column(db.Integer, nullable=False, default=0)
    preference_profile = db.Column(db.String(32), default="balanced")
    tags = db.Column(db.JSON, default=list)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    procurement = db.relationship("Procurement", back_populates="matches")
    supplier = db.relationship("Supplier", back_populates="matches")
