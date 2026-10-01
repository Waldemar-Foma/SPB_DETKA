from backend.extensions import db


class Supplier(db.Model):
    __tablename__ = "suppliers"

    id = db.Column(db.Integer, primary_key=True)
    inn = db.Column(db.String(12), unique=True, nullable=False, index=True)
    ogrn = db.Column(db.String(15))
    name = db.Column(db.String(255), nullable=False)
    # Базовая/legacy роль; в выдаче роль уточняется role_classifier по контексту закупки.
    company_type = db.Column(db.String(64), nullable=False, default="Поставщик")
    region = db.Column(db.String(128), nullable=False, index=True)
    address = db.Column(db.Text)
    website = db.Column(db.String(255))
    phone = db.Column(db.String(64))
    email = db.Column(db.String(128))
    years_on_market = db.Column(db.Integer)
    is_verified = db.Column(db.Boolean, default=True)
    revenue_annual = db.Column(db.Numeric(15, 2))
    okpd2_codes = db.Column(db.Text)  # CSV-коды из истории участия/побед
    specialization = db.Column(db.Text)  # агрегированный профиль ТРУ для embeddings
    primary_okved = db.Column(db.String(32), index=True)

    # Оффлайн-обогащение открытыми реестрами.
    is_gisp_manufacturer = db.Column(db.Boolean, default=False, nullable=False)
    is_sme = db.Column(db.Boolean, default=False, nullable=False)
    data_source = db.Column(db.String(64), default="demo")
    enrichment_updated_at = db.Column(db.DateTime)
    contact_lookup_at = db.Column(db.DateTime)

    # Исторические признаки из предоставленных датасетов.
    participation_count = db.Column(db.Integer, default=0, nullable=False)
    wins_count = db.Column(db.Integer, default=0, nullable=False)
    unique_won_okpd2 = db.Column(db.Integer, default=0, nullable=False)

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
    reviews = db.relationship(
        "SupplierReview",
        back_populates="supplier",
        cascade="all, delete-orphan",
    )
    external_mentions = db.relationship(
        "ExternalMention",
        back_populates="supplier",
        cascade="all, delete-orphan",
    )

    def to_card(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "inn": self.inn,
            "company_type": self.company_type,
            "region": self.region,
            "years_on_market": self.years_on_market,
            "is_verified": self.is_verified,
            "is_gisp_manufacturer": self.is_gisp_manufacturer,
            "is_sme": self.is_sme,
            "wins_count": self.wins_count,
            "participation_count": self.participation_count,
        }

    def to_details(self) -> dict:
        return {
            **self.to_card(),
            "ogrn": self.ogrn,
            "primary_okved": self.primary_okved,
            "specialization": self.specialization,
            "data_source": self.data_source,
            "contacts": {
                "website": self.website,
                "phone": self.phone,
                "email": self.email,
                "address": self.address,
            },
            "coords": {"lat": self.lat, "lon": self.lon},
        }
