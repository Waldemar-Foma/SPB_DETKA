from backend.extensions import db


class SupplierContract(db.Model):
    """Историческое участие/победа поставщика в лоте."""
    __tablename__ = "supplier_contracts"

    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(
        db.Integer,
        db.ForeignKey("suppliers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contract_number = db.Column(db.String(64))
    lot_id = db.Column(db.String(64), index=True)
    year = db.Column(db.Integer, nullable=False, index=True)
    amount = db.Column(db.Numeric(15, 2), nullable=False, default=0)
    subject = db.Column(db.Text)
    product_name = db.Column(db.Text)
    okpd2_code = db.Column(db.String(32), index=True)
    customer_inn = db.Column(db.String(12), index=True)
    is_winner = db.Column(db.Boolean, default=True, nullable=False)

    supplier = db.relationship("Supplier", back_populates="contracts")
