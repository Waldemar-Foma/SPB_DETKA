from backend.extensions import db


class SupplierContract(db.Model):
    """Ранее исполненный контракт компании."""
    __tablename__ = "supplier_contracts"

    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(
        db.Integer,
        db.ForeignKey("suppliers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contract_number = db.Column(db.String(64))
    year = db.Column(db.Integer, nullable=False, index=True)
    amount = db.Column(db.Numeric(15, 2), nullable=False)
    subject = db.Column(db.Text)

    supplier = db.relationship("Supplier", back_populates="contracts")