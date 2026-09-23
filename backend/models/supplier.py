from backend.extensions import db


class Supplier(db.Model):
    __tablename__ = "suppliers"

    id = db.Column(db.Integer, primary_key=True)
    inn = db.Column(db.String(12), unique=True, nullable=False, index=True)
    ogrn = db.Column(db.String(15))
    name = db.Column(db.String(255), nullable=False)
    company_type = db.Column(db.String(64), nullable=False)
    region = db.Column(db.String(128), nullable=False, index=True)
    address = db.Column(db.Text)
    website = db.Column(db.String(255))
    phone = db.Column(db.String(64))
    email = db.Column(db.String(128))
    years_on_market = db.Column(db.Integer)
    is_verified = db.Column(db.Boolean, default=True)
    revenue_annual = db.Column(db.Numeric(15, 2))
    okpd2_codes = db.Column(db.Text)  # CSV-строка для матчинга
    lat = db.Column(db.Float)
    lon = db.Column(db.Float)

    contracts = db.relationship(
        "SupplierContract",
        back_populates="supplier",
        cascade="all, delete-orphan",
    )
    matches = db.relationship(
        "MatchingResult",
        back_populates="supplier",
        cascade="all, delete-orphan",
    )

    def to_card(self) -> dict:
        """Краткая карточка для ленты результатов."""
        return {
            "id": self.id,
            "name": self.name,
            "inn": self.inn,
            "company_type": self.company_type,
            "region": self.region,
            "years_on_market": self.years_on_market,
            "is_verified": self.is_verified,
        }

    def to_details(self) -> dict:
        """Полный профиль для боковой панели."""
        return {
            **self.to_card(),
            "ogrn": self.ogrn,
            "contacts": {
                "website": self.website,
                "phone": self.phone,
                "email": self.email,
                "address": self.address,
            },
            "coords": {"lat": self.lat, "lon": self.lon},
        }