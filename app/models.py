# app/models.py
from __future__ import annotations

import enum
import secrets
import uuid
from datetime import date, datetime, timezone, timedelta

import sqlalchemy as sa
from flask_login import UserMixin
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import INET, UUID, JSONB
from sqlalchemy.ext.mutable import MutableDict

from .extensions import db


# Use **naive UTC** everywhere because your DB columns are "timestamp without time zone".
# (Postgres stores no TZ info, so we standardize on UTC-naive in app code.)
def utcnow_naive() -> datetime:
    return datetime.utcnow()


# =========================================================
# User model (Authentication + Roles)
# =========================================================
class User(UserMixin, db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)

    # Identity
    name = db.Column(db.String(120), nullable=False)

    # IMPORTANT:
    # Keep unique=True + index=True, but also pin the constraint name so Alembic stops
    # churning between user_email_key vs ix_user_email.
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), unique=True, nullable=True)

    # Auth
    password_hash = db.Column(db.String(255), nullable=False)

    # Roles (super-admin/admin/staff/buyer/farmer/transporter/service)
    role = db.Column(db.String(30), nullable=False, default="buyer")
    is_admin = db.Column(db.Boolean, default=False, nullable=False)

    # Account lifecycle / security
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)
    password_changed_at = db.Column(db.DateTime, nullable=True)

    failed_login_attempts = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)

    last_login_at = db.Column(db.DateTime, nullable=True)

    # Terms & Conditions acceptance (external users)
    accepted_terms = db.Column(db.Boolean, nullable=False, default=False)
    accepted_terms_at = db.Column(db.DateTime, nullable=True)
    terms_version = db.Column(db.String(20), nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=utcnow_naive)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )

    __table_args__ = (
        db.UniqueConstraint("email", name="user_email_key"),
        db.Index("ix_user_email", "email", unique=True),
    )

    def __repr__(self) -> str:
        return f"<User {self.id} {self.email}>"


# =========================================================
# Buyer (Business profile) + optional login link
# =========================================================
class Buyer(db.Model):
    __tablename__ = "buyer"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=True)
    user = db.relationship("User", foreign_keys=[user_id], lazy="joined")

    name = db.Column(db.String(160), nullable=False)
    phone = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    tax_pin = db.Column(db.String(60), nullable=True)

    created_at = db.Column(db.DateTime, default=utcnow_naive, nullable=False)

    def __repr__(self) -> str:
        return f"<Buyer {self.id} {self.name}>"


# =========================================================
# Documents (LOI, agreements, specs) + signatures
# =========================================================
class Document(db.Model):
    __tablename__ = "document"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    buyer_id = db.Column(
        db.Integer,
        db.ForeignKey("buyer.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    buyer = db.relationship("Buyer", foreign_keys=[buyer_id], lazy="joined")

    doc_type = db.Column(db.String(50), nullable=False, index=True)  # indexed in DB
    title = db.Column(db.String(200), nullable=False)

    status = db.Column(db.String(30), nullable=False, default="draft", index=True)  # indexed in DB
    version = db.Column(db.Integer, nullable=False, default=1)

    storage_key = db.Column(db.String(500), nullable=True)
    file_sha256 = db.Column(db.String(64), nullable=True)

    # IMPORTANT:
    # Use MutableDict so SQLAlchemy tracks in-place JSON edits and persists them.
    # DB column is jsonb (already migrated).
    payload = db.Column(MutableDict.as_mutable(JSONB), nullable=True)

    # DB column is "timestamp without time zone" (naive datetime)
    issued_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)

    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by = db.relationship("User", foreign_keys=[created_by_user_id], lazy="joined")

    # Match DB defaults: now()
    created_at = db.Column(db.DateTime, nullable=False, server_default=sa.text("now()"))
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=sa.text("now()"),
        # DB already has a trigger trg_set_document_updated_at() for updated_at;
        # keep ORM onupdate too (harmless; helps when trigger isn't present in some env).
        onupdate=utcnow_naive,
    )

    # IMPORTANT: match DB schema
    # DB: buyer_sign_token varchar(128), indexed, NOT unique constraint.
    buyer_sign_token = db.Column(db.String(128), nullable=True, index=True)
    buyer_sign_token_expires_at = db.Column(db.DateTime, nullable=True)

    buyer_signed_at = db.Column(db.DateTime, nullable=True)
    buyer_sign_name = db.Column(db.String(160), nullable=True)  # DB is varchar(160)
    buyer_sign_email = db.Column(db.String(120), nullable=True)

    buyer_sign_ip = db.Column(db.String(64), nullable=True)
    buyer_sign_user_agent = db.Column(db.String(255), nullable=True)

    def new_sign_token(self, hours: int = 72) -> str:
        token = secrets.token_urlsafe(32)  # ~43 chars
        self.buyer_sign_token = token
        # Store as naive UTC to match DB type
        self.buyer_sign_token_expires_at = utcnow_naive() + timedelta(hours=hours)
        return token

    def is_sign_token_valid(self) -> bool:
        if not self.buyer_sign_token or not self.buyer_sign_token_expires_at:
            return False
        return utcnow_naive() <= self.buyer_sign_token_expires_at

    __table_args__ = (
        db.UniqueConstraint(
            "buyer_id",
            "doc_type",
            "version",
            name="uq_document_buyer_type_version",
        ),
        db.Index(
            "ix_document_buyer_type_status",
            "buyer_id",
            "doc_type",
            "status",
        ),
    )

    signatures = db.relationship(
        "DocumentSignature",
        back_populates="document",
        lazy="select",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Document {self.id} {self.doc_type} v{self.version} {self.status}>"


class DocumentSignature(db.Model):
    __tablename__ = "document_signature"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    document_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("document.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document = db.relationship("Document", back_populates="signatures", lazy="joined")

    signer_type = db.Column(db.String(30), nullable=False)  # buyer|rizara_admin|rizara_staff

    signed_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    signed_by = db.relationship("User", foreign_keys=[signed_by_user_id], lazy="joined")

    sign_method = db.Column(db.String(30), nullable=False)  # drawn|typed|docusign
    signer_name = db.Column(db.String(160), nullable=False)
    signer_email = db.Column(db.String(255), nullable=True)

    signature_image_storage_key = db.Column(db.String(500), nullable=True)
    typed_consent_text = db.Column(db.Text, nullable=True)

    signed_at = db.Column(db.DateTime, nullable=False, server_default=sa.text("now()"))
    ip_address = db.Column(INET, nullable=True)
    user_agent = db.Column(db.Text, nullable=True)

    __table_args__ = (
        db.CheckConstraint(
            "signer_type in ('buyer','rizara_admin','rizara_staff')",
            name="ck_docsig_signer_type",
        ),
        db.CheckConstraint(
            "sign_method in ('drawn','typed','docusign')",
            name="ck_docsig_sign_method",
        ),
    )

    def __repr__(self) -> str:
        return f"<DocumentSignature {self.id} {self.signer_type} {self.sign_method}>"


DOCUMENT_STATUSES = {"draft", "buyer_signed", "executed", "expired", "void"}

ALLOWED_TRANSITIONS = {
    "draft": {"buyer_signed", "void"},
    "buyer_signed": {"executed", "void"},
    "executed": {"void"},
    "expired": {"void"},
    "void": set(),
}

# =========================================================
# Market Purchase Statuses
# =========================================================
MARKET_PURCHASE_STATUSES = {
    "draft",
    "confirmed",
    "received",
    "cancelled",
}


def can_transition(current: str, target: str) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())


# =========================================================
# Farmer model
# =========================================================
class Farmer(db.Model):
    __tablename__ = "farmer"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    county = db.Column(db.String(100), nullable=False)
    ward = db.Column(db.String(100), nullable=False)
    village = db.Column(db.String(120), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    location_notes = db.Column(db.String(255), nullable=True)
    onboarded_at = db.Column(db.DateTime, default=utcnow_naive)

    goats = db.relationship("Goat", backref="farmer", lazy=True, cascade="all, delete-orphan")
    sheep = db.relationship("Sheep", backref="farmer", lazy=True, cascade="all, delete-orphan")
    cattle = db.relationship("Cattle", backref="farmer", lazy=True, cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Farmer {self.id} {self.name}>"


# =========================================================
# Base Animal (abstract)
# =========================================================
class BaseAnimal(db.Model):
    __abstract__ = True

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    farmer_tag = db.Column(db.String(64), nullable=False)
    rizara_id = db.Column(db.String(64), unique=True, nullable=False)

    sex = db.Column(db.String(10), nullable=True)
    breed = db.Column(db.String(50), nullable=True)
    estimated_dob = db.Column(db.Date, nullable=True)

    status = db.Column(db.String(30), nullable=False, default="on_farm")

    farmer_id = db.Column(db.Integer, db.ForeignKey("farmer.id"), nullable=False)

    created_at = db.Column(db.DateTime, default=utcnow_naive)

    # Operational flags
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # Aggregation snapshot (purchase point)
    aggregated_at = db.Column(db.DateTime, nullable=True)
    aggregated_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    live_weight_kg = db.Column(db.Float, nullable=True)
    weight_method = db.Column(db.String(20), nullable=True)  # scale | estimated | tape | other
    purchase_price_per_head = db.Column(db.Float, nullable=True)
    purchase_currency = db.Column(db.String(10), default="KES")


# =========================================================
# Goat model
# =========================================================
class Goat(BaseAnimal):
    __tablename__ = "goat"

    aggregation_batch_id = db.Column(db.Integer, db.ForeignKey("aggregation_batch.id"), nullable=True)
    aggregation_batch = db.relationship("AggregationBatch", back_populates="goats")

    processing_batches = db.relationship(
        "ProcessingBatch",
        secondary="processing_goats",
        back_populates="goats",
    )

    def __repr__(self) -> str:
        return f"<Goat {self.id} {self.rizara_id} {self.status}>"


# =========================================================
# Sheep model
# =========================================================
class Sheep(BaseAnimal):
    __tablename__ = "sheep"

    aggregation_batch_id = db.Column(db.Integer, db.ForeignKey("aggregation_batch.id"), nullable=True)
    aggregation_batch = db.relationship("AggregationBatch", back_populates="sheep")

    processing_batches = db.relationship(
        "ProcessingBatch",
        secondary="processing_sheep",
        back_populates="sheep",
    )

    def __repr__(self) -> str:
        return f"<Sheep {self.id} {self.rizara_id} {self.status}>"


# =========================================================
# Cattle model
# =========================================================
class Cattle(BaseAnimal):
    __tablename__ = "cattle"

    aggregation_batch_id = db.Column(db.Integer, db.ForeignKey("aggregation_batch.id"), nullable=True)
    aggregation_batch = db.relationship("AggregationBatch", back_populates="cattle")

    processing_batches = db.relationship(
        "ProcessingBatch",
        secondary="processing_cattle",
        back_populates="cattle",
    )

    def __repr__(self) -> str:
        return f"<Cattle {self.id} {self.rizara_id} {self.status}>"


# =========================================================
# Aggregation Batch (single animal type per batch)
# =========================================================
class AggregationBatch(db.Model):
    __tablename__ = "aggregation_batch"

    id = db.Column(db.Integer, primary_key=True)

    # Batch identity
    animal_type = db.Column(db.String(20), nullable=False)  # goat, sheep, cattle
    site_name = db.Column(db.String(120), nullable=False)
    date_received = db.Column(db.Date, default=date.today, nullable=False)

    # Lifecycle
    is_locked = db.Column(db.Boolean, default=False, nullable=False)
    locked_at = db.Column(db.DateTime, nullable=True)

    # Audit
    created_at = db.Column(db.DateTime, default=utcnow_naive, nullable=False)

    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False,
    )
    created_by = db.relationship(
        "User",
        foreign_keys=[created_by_user_id],
        lazy="joined",
    )

    # On-farm animals aggregated into this batch
    goats = db.relationship(
        "Goat",
        back_populates="aggregation_batch",
        lazy="select",
    )
    sheep = db.relationship(
        "Sheep",
        back_populates="aggregation_batch",
        lazy="select",
    )
    cattle = db.relationship(
        "Cattle",
        back_populates="aggregation_batch",
        lazy="select",
    )

    # Direct market procurement attached to this batch
    market_purchases = db.relationship(
        "MarketPurchase",
        back_populates="aggregation_batch",
        lazy="select",
        cascade="all, delete-orphan",
    )
    market_purchase_expenses = db.relationship(
        "MarketPurchaseExpense",
        back_populates="aggregation_batch",
        lazy="select",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        db.CheckConstraint(
            "animal_type in ('goat','sheep','cattle')",
            name="ck_aggregation_batch_animal_type",
        ),
    )

    @property
    def farm_headcount(self) -> int:
        if self.animal_type == "goat":
            return len(self.goats)
        if self.animal_type == "sheep":
            return len(self.sheep)
        if self.animal_type == "cattle":
            return len(self.cattle)
        return 0

    @property
    def market_headcount(self) -> int:
        return sum((purchase.total_headcount or 0) for purchase in self.market_purchases)

    @property
    def total_headcount(self) -> int:
        return self.farm_headcount + self.market_headcount

    @property
    def market_purchase_cost_total(self) -> float:
        return float(sum((purchase.total_purchase_cost or 0.0) for purchase in self.market_purchases))

    @property
    def market_expense_cost_total(self) -> float:
        return float(sum((purchase.total_expense_cost or 0.0) for purchase in self.market_purchases))

    @property
    def direct_market_cost_total(self) -> float:
        return self.market_purchase_cost_total + self.market_expense_cost_total

    @property
    def estimated_market_carcass_weight_kg(self) -> float:
        return float(sum((purchase.estimated_total_carcass_weight_kg or 0.0) for purchase in self.market_purchases))

    def __repr__(self) -> str:
        return f"<AggregationBatch {self.id} {self.animal_type} {self.site_name}>"


# =========================================================
# Processing association tables (many-to-many)
# =========================================================
processing_goats = db.Table(
    "processing_goats",
    db.Column(
        "processing_batch_id",
        db.Integer,
        db.ForeignKey("processing_batch.id"),
        primary_key=True,
    ),
    db.Column(
        "goat_id",
        UUID(as_uuid=True),
        db.ForeignKey("goat.id"),
        primary_key=True,
    ),
)

processing_sheep = db.Table(
    "processing_sheep",
    db.Column(
        "processing_batch_id",
        db.Integer,
        db.ForeignKey("processing_batch.id"),
        primary_key=True,
    ),
    db.Column(
        "sheep_id",
        UUID(as_uuid=True),
        db.ForeignKey("sheep.id"),
        primary_key=True,
    ),
)

processing_cattle = db.Table(
    "processing_cattle",
    db.Column(
        "processing_batch_id",
        db.Integer,
        db.ForeignKey("processing_batch.id"),
        primary_key=True,
    ),
    db.Column(
        "cattle_id",
        UUID(as_uuid=True),
        db.ForeignKey("cattle.id"),
        primary_key=True,
    ),
)

# =========================================================
# Processing Batch (single animal type per batch)
# =========================================================
class ProcessingBatch(db.Model):
    __tablename__ = "processing_batch"

    id = db.Column(db.Integer, primary_key=True)
    animal_type = db.Column(db.String(20), nullable=False)  # goat, sheep, cattle
    facility = db.Column(db.String(120), nullable=False)
    slaughter_date = db.Column(db.Date, nullable=True)
    halal_cert_ref = db.Column(db.String(120), nullable=True)

    is_locked = db.Column(db.Boolean, default=False)
    locked_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=utcnow_naive)

    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_by = db.relationship("User", foreign_keys=[created_by_user_id], lazy="joined")

    goats = db.relationship("Goat", secondary=processing_goats, back_populates="processing_batches")
    sheep = db.relationship("Sheep", secondary=processing_sheep, back_populates="processing_batches")
    cattle = db.relationship("Cattle", secondary=processing_cattle, back_populates="processing_batches")

    def __repr__(self) -> str:
        return f"<ProcessingBatch {self.id} {self.animal_type}>"


# =========================================================
# Traceability Records
# =========================================================
class TraceabilityRecord(db.Model):
    __tablename__ = "traceability_record"

    id = db.Column(db.Integer, primary_key=True)
    animal_type = db.Column(db.String(20), nullable=False)  # goat, sheep, cattle
    animal_id = db.Column(UUID(as_uuid=True), nullable=False)
    qr_code_data = db.Column(db.Text, nullable=False)
    public_url = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow_naive)


# =========================================================
# ContactMessage
# =========================================================
class ContactMessage(db.Model):
    __tablename__ = "contact_messages"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(200), nullable=True)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="new")  # new, reviewed, closed
    created_at = db.Column(db.DateTime, default=utcnow_naive)


# =========================================================
# OrderRequest
# =========================================================
class OrderRequest(db.Model):
    __tablename__ = "order_requests"

    id = db.Column(db.Integer, primary_key=True)

    buyer_id = db.Column(db.Integer, db.ForeignKey("buyer.id"), nullable=True)
    buyer = db.relationship("Buyer", foreign_keys=[buyer_id], lazy="joined")

    buyer_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    product = db.Column(db.String(120), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    delivery_location = db.Column(db.String(200), nullable=False)
    notes = db.Column(db.Text, nullable=True)

    status = db.Column(db.String(20), default="new")  # new, reviewed, approved, rejected
    created_at = db.Column(db.DateTime, default=utcnow_naive)


# =========================================================
# AnimalEvent (generic)
# =========================================================
class AnimalEvent(db.Model):
    __tablename__ = "animal_event"

    id = db.Column(db.Integer, primary_key=True)

    animal_type = db.Column(db.String(20), nullable=False)  # goat, sheep, cattle
    animal_id = db.Column(UUID(as_uuid=True), nullable=False)

    event_type = db.Column(db.String(50), nullable=False)
    event_datetime = db.Column(db.DateTime, default=utcnow_naive, nullable=False)

    performed_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    from_farmer_id = db.Column(db.Integer, db.ForeignKey("farmer.id"), nullable=True)
    to_farmer_id = db.Column(db.Integer, db.ForeignKey("farmer.id"), nullable=True)

    from_location = db.Column(db.String(120), nullable=True)
    to_location = db.Column(db.String(120), nullable=True)

    notes = db.Column(db.Text, nullable=True)
    attachment_url = db.Column(db.String(255), nullable=True)

    is_verified = db.Column(db.Boolean, default=True, nullable=False)
    verified_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    verified_at = db.Column(db.DateTime, nullable=True)


# =========================================================
# AggregationCost
# =========================================================
class AggregationCost(db.Model):
    __tablename__ = "aggregation_cost"

    id = db.Column(db.Integer, primary_key=True)
    aggregation_batch_id = db.Column(db.Integer, db.ForeignKey("aggregation_batch.id"), nullable=False)

    cost_type = db.Column(db.String(30), nullable=False)  # transport, feed, treatment, misc
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default="KES")

    incurred_date = db.Column(db.Date, default=date.today, nullable=False)
    paid_to = db.Column(db.String(120), nullable=True)
    reference = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow_naive, nullable=False)


# =========================================================
# AnimalHealthEvent
# =========================================================
class AnimalHealthEvent(db.Model):
    __tablename__ = "animal_health_event"

    id = db.Column(db.Integer, primary_key=True)

    animal_type = db.Column(db.String(20), nullable=False)
    animal_id = db.Column(UUID(as_uuid=True), nullable=False)

    aggregation_batch_id = db.Column(db.Integer, db.ForeignKey("aggregation_batch.id"), nullable=False)

    diagnosis = db.Column(db.String(200), nullable=True)
    treatment = db.Column(db.String(200), nullable=True)

    cost = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(10), default="KES")

    treated_by = db.Column(db.String(120), nullable=True)
    event_date = db.Column(db.Date, default=date.today, nullable=False)
    notes = db.Column(db.Text, nullable=True)

    recorded_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow_naive, nullable=False)


# =========================================================
# ProcessingYield
# =========================================================
class ProcessingYield(db.Model):
    __tablename__ = "processing_yield"

    id = db.Column(db.Integer, primary_key=True)
    processing_batch_id = db.Column(db.Integer, db.ForeignKey("processing_batch.id"), unique=True, nullable=False)

    total_carcass_weight_kg = db.Column(db.Float, nullable=False)
    parts_included_in_batch_sale = db.Column(db.Boolean, default=True, nullable=False)
    parts_sold_separately = db.Column(db.Boolean, default=False, nullable=False)
    parts_notes = db.Column(db.Text, nullable=True)

    recorded_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    recorded_at = db.Column(db.DateTime, default=utcnow_naive, nullable=False)


# =========================================================
# ProcessingBatchSale
# =========================================================
class ProcessingBatchSale(db.Model):
    __tablename__ = "processing_batch_sale"

    id = db.Column(db.Integer, primary_key=True)
    processing_batch_id = db.Column(db.Integer, db.ForeignKey("processing_batch.id"), unique=True, nullable=False)

    buyer_id = db.Column(db.Integer, db.ForeignKey("buyer.id"), nullable=False)
    buyer = db.relationship("Buyer", foreign_keys=[buyer_id], lazy="joined")

    total_sale_price = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default="KES")

    sale_date = db.Column(db.Date, default=date.today, nullable=False)

    notes = db.Column(db.Text, nullable=True)

    recorded_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    recorded_by = db.relationship("User", foreign_keys=[recorded_by_user_id], lazy="joined")

    created_at = db.Column(db.DateTime, default=utcnow_naive, nullable=False)


# =========================================================
# Invoice Status (Enum)
# =========================================================
class InvoiceStatus(enum.Enum):
    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"
    VOID = "void"


# =========================================================
# Invoice
# =========================================================
class Invoice(db.Model):
    __tablename__ = "invoice"

    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(40), unique=True, nullable=False)

    buyer_id = db.Column(db.Integer, db.ForeignKey("buyer.id", ondelete="CASCADE"), nullable=False, index=True)
    buyer = db.relationship("Buyer", foreign_keys=[buyer_id], lazy="joined")

    processing_batch_sale_id = db.Column(
        db.Integer, db.ForeignKey("processing_batch_sale.id"), unique=True, nullable=False
    )
    sale = db.relationship("ProcessingBatchSale", foreign_keys=[processing_batch_sale_id], lazy="joined")

    issue_date = db.Column(db.Date, default=date.today, nullable=False)
    due_date = db.Column(db.Date, nullable=True)

    status = db.Column(
        SAEnum(
            InvoiceStatus,
            name="invoice_status",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
            native_enum=False,
        ),
        nullable=False,
        default=InvoiceStatus.ISSUED,
    )

    issued_at = db.Column(db.DateTime, nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    voided_at = db.Column(db.DateTime, nullable=True)

    subtotal = db.Column(db.Float, default=0.0, nullable=False)
    tax = db.Column(db.Float, default=0.0, nullable=False)
    total = db.Column(db.Float, default=0.0, nullable=False)

    notes = db.Column(db.Text, nullable=True)
    terms = db.Column(db.Text, nullable=True)

    issued_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    issued_by = db.relationship("User", foreign_keys=[issued_by_user_id], lazy="joined")

    items = db.relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan", lazy="select")

    created_at = db.Column(db.DateTime, default=utcnow_naive, nullable=False)

    def __repr__(self) -> str:
        return f"<Invoice {self.id} {self.invoice_number} {self.status}>"


# =========================================================
# InvoiceItem
# =========================================================
class InvoiceItem(db.Model):
    __tablename__ = "invoice_item"

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoice.id"), nullable=False)

    invoice = db.relationship("Invoice", back_populates="items", lazy="joined")

    description = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Float, default=1.0, nullable=False)
    unit_price = db.Column(db.Float, default=0.0, nullable=False)
    line_total = db.Column(db.Float, default=0.0, nullable=False)


# =========================================================
# Vendor
# =========================================================
class Vendor(db.Model):
    __tablename__ = "vendor"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    phone = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(120), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow_naive, nullable=False)


# =========================================================
# ExpenseCategory
# =========================================================
class ExpenseCategory(db.Model):
    __tablename__ = "expense_category"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    expense_class = db.Column(db.String(20), default="overhead", nullable=False)  # overhead/direct


# =========================================================
# Expense
# =========================================================
class Expense(db.Model):
    __tablename__ = "expense"

    id = db.Column(db.Integer, primary_key=True)
    expense_date = db.Column(db.Date, default=date.today, nullable=False)

    category_id = db.Column(db.Integer, db.ForeignKey("expense_category.id"), nullable=False)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendor.id"), nullable=True)

    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default="KES")

    payment_method = db.Column(db.String(30), nullable=True)  # cash/mpesa/bank
    reference = db.Column(db.String(120), nullable=True)
    cost_center = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    attachment_url = db.Column(db.String(255), nullable=True)

    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow_naive, nullable=False)


# =========================================================
# Asset
# =========================================================
class Asset(db.Model):
    __tablename__ = "asset"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    asset_type = db.Column(db.String(60), nullable=False)  # vehicle, scale, equipment...
    ownership_type = db.Column(db.String(20), default="owned", nullable=False)  # owned/leased

    purchase_date = db.Column(db.Date, nullable=True)
    purchase_cost = db.Column(db.Float, nullable=True)
    currency = db.Column(db.String(10), default="KES")

    location = db.Column(db.String(120), nullable=True)
    status = db.Column(db.String(20), default="active", nullable=False)  # active/repair/disposed

    vendor_id = db.Column(db.Integer, db.ForeignKey("vendor.id"), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=utcnow_naive, nullable=False)


# =========================================================
# AssetMaintenance
# =========================================================
class AssetMaintenance(db.Model):
    __tablename__ = "asset_maintenance"

    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("asset.id"), nullable=False)

    maintenance_date = db.Column(db.Date, default=date.today, nullable=False)
    cost = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(10), default="KES")

    notes = db.Column(db.Text, nullable=True)
    attachment_url = db.Column(db.String(255), nullable=True)

    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow_naive, nullable=False)

# =========================================================
# MarketPurchase
# Direct external procurement into an existing aggregation batch
# =========================================================
class MarketPurchase(db.Model):
    __tablename__ = "market_purchase"

    id = db.Column(db.Integer, primary_key=True)

    aggregation_batch_id = db.Column(
        db.Integer,
        db.ForeignKey("aggregation_batch.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    aggregation_batch = db.relationship(
        "AggregationBatch",
        back_populates="market_purchases",
        lazy="joined",
    )

    animal_type = db.Column(db.String(20), nullable=False)  # goat, sheep, cattle
    purchase_date = db.Column(db.Date, default=date.today, nullable=False)

    market_name = db.Column(db.String(120), nullable=False)
    vendor_name = db.Column(db.String(160), nullable=True)
    broker_name = db.Column(db.String(160), nullable=True)

    reference = db.Column(db.String(120), nullable=True)

    status = db.Column(
        db.String(20),
        nullable=False,
        default="draft",
        index=True,
    )

    notes = db.Column(db.Text, nullable=True)

    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )
    created_by = db.relationship(
        "User",
        foreign_keys=[created_by_user_id],
        lazy="joined",
    )

    created_at = db.Column(
        db.DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    updated_at = db.Column(
        db.DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    lines = db.relationship(
        "MarketPurchaseLine",
        back_populates="market_purchase",
        lazy="select",
        cascade="all, delete-orphan",
    )

    expenses = db.relationship(
        "MarketPurchaseExpense",
        back_populates="market_purchase",
        lazy="select",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        db.CheckConstraint(
            "animal_type in ('goat','sheep','cattle')",
            name="ck_market_purchase_animal_type",
        ),
        db.CheckConstraint(
            "status in ('draft','confirmed','received','cancelled')",
            name="ck_market_purchase_status",
        ),
        db.Index(
            "ix_market_purchase_batch_animal_status",
            "aggregation_batch_id",
            "animal_type",
            "status",
        ),
    )

    @property
    def total_headcount(self) -> int:
        return sum((line.qty or 0) for line in self.lines)

    @property
    def total_purchase_cost(self) -> float:
        return float(sum((line.total_price_kes or 0.0) for line in self.lines))

    @property
    def total_expense_cost(self) -> float:
        return float(sum((expense.amount or 0.0) for expense in self.expenses))

    @property
    def total_cost(self) -> float:
        return self.total_purchase_cost + self.total_expense_cost

    @property
    def average_price_per_head(self) -> float:
        if not self.total_headcount:
            return 0.0
        return float(self.total_purchase_cost / self.total_headcount)

    @property
    def estimated_total_live_weight_kg(self) -> float:
        return float(
            sum(
                (line.qty or 0) * (line.estimated_live_weight_per_head_kg or 0.0)
                for line in self.lines
            )
        )

    @property
    def estimated_total_carcass_weight_kg(self) -> float:
        return float(
            sum(
                (line.qty or 0) * (line.estimated_carcass_weight_per_head_kg or 0.0)
                for line in self.lines
            )
        )

    def can_transition(self, target: str) -> bool:
        transitions = {
            "draft": {"confirmed", "cancelled"},
            "confirmed": {"received", "cancelled"},
            "received": set(),
            "cancelled": set(),
        }
        return target in transitions.get(self.status, set())

    def __repr__(self) -> str:
        return f"<MarketPurchase {self.id} {self.market_name} {self.animal_type} {self.status}>"

# =========================================================
# MarketPurchaseLine
# Bulk line items from market buying, linked to one purchase event
# =========================================================
class MarketPurchaseLine(db.Model):
    __tablename__ = "market_purchase_line"

    id = db.Column(db.Integer, primary_key=True)

    market_purchase_id = db.Column(
        db.Integer,
        db.ForeignKey("market_purchase.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    market_purchase = db.relationship(
        "MarketPurchase",
        back_populates="lines",
        lazy="joined",
    )

    qty = db.Column(db.Integer, nullable=False)
    unit_price_kes = db.Column(db.Float, nullable=False)
    total_price_kes = db.Column(db.Float, nullable=False)

    estimated_live_weight_per_head_kg = db.Column(db.Float, nullable=True)
    estimated_carcass_weight_per_head_kg = db.Column(db.Float, nullable=True)

    avg_age_months = db.Column(db.Integer, nullable=True)
    weight_method = db.Column(
        db.String(20),
        nullable=True,
    )  # estimated | scale | tape | other

    notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(
        db.DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    updated_at = db.Column(
        db.DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    __table_args__ = (
        db.CheckConstraint(
            "qty > 0",
            name="ck_market_purchase_line_qty_positive",
        ),
        db.CheckConstraint(
            "unit_price_kes >= 0",
            name="ck_market_purchase_line_unit_price_non_negative",
        ),
        db.CheckConstraint(
            "total_price_kes >= 0",
            name="ck_market_purchase_line_total_non_negative",
        ),
        db.CheckConstraint(
            "(estimated_live_weight_per_head_kg is null) or (estimated_live_weight_per_head_kg >= 0)",
            name="ck_market_purchase_line_live_weight_non_negative",
        ),
        db.CheckConstraint(
            "(estimated_carcass_weight_per_head_kg is null) or (estimated_carcass_weight_per_head_kg >= 0)",
            name="ck_market_purchase_line_carcass_weight_non_negative",
        ),
        db.CheckConstraint(
            "(avg_age_months is null) or (avg_age_months >= 0)",
            name="ck_market_purchase_line_avg_age_non_negative",
        ),
        db.CheckConstraint(
            "(weight_method is null) or (weight_method in ('estimated','scale','tape','other'))",
            name="ck_market_purchase_line_weight_method",
        ),
    )

    @property
    def average_price_per_head(self) -> float:
        if not self.qty:
            return 0.0
        return float((self.total_price_kes or 0.0) / self.qty)

    @property
    def estimated_total_live_weight_kg(self) -> float:
        if self.estimated_live_weight_per_head_kg is None:
            return 0.0
        return float(self.qty * self.estimated_live_weight_per_head_kg)

    @property
    def estimated_total_carcass_weight_kg(self) -> float:
        if self.estimated_carcass_weight_per_head_kg is None:
            return 0.0
        return float(self.qty * self.estimated_carcass_weight_per_head_kg)

    @property
    def estimated_live_cost_per_kg(self) -> float:
        total_live_weight = self.estimated_total_live_weight_kg
        if total_live_weight <= 0:
            return 0.0
        return float((self.total_price_kes or 0.0) / total_live_weight)

    @property
    def estimated_carcass_cost_per_kg(self) -> float:
        total_carcass_weight = self.estimated_total_carcass_weight_kg
        if total_carcass_weight <= 0:
            return 0.0
        return float((self.total_price_kes or 0.0) / total_carcass_weight)

    def __repr__(self) -> str:
        return (
            f"<MarketPurchaseLine {self.id} "
            f"qty={self.qty} unit_price_kes={self.unit_price_kes}>"
        )


# =========================================================
# MarketPurchaseExpense
# Non-animal direct procurement costs linked to a market purchase
# =========================================================
class MarketPurchaseExpense(db.Model):
    __tablename__ = "market_purchase_expense"

    id = db.Column(db.Integer, primary_key=True)

    aggregation_batch_id = db.Column(
        db.Integer,
        db.ForeignKey("aggregation_batch.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    aggregation_batch = db.relationship(
        "AggregationBatch",
        back_populates="market_purchase_expenses",
        lazy="joined",
    )

    market_purchase_id = db.Column(
        db.Integer,
        db.ForeignKey("market_purchase.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    market_purchase = db.relationship(
        "MarketPurchase",
        back_populates="expenses",
        lazy="joined",
    )

    expense_type = db.Column(
        db.String(40),
        nullable=False,
        index=True,
    )  # transport, documentation, broker, accommodation, meals, misc

    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default="KES", nullable=False)

    incurred_date = db.Column(
        db.Date,
        default=date.today,
        nullable=False,
    )

    paid_to = db.Column(db.String(160), nullable=True)
    reference = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )
    created_by = db.relationship(
        "User",
        foreign_keys=[created_by_user_id],
        lazy="joined",
    )

    created_at = db.Column(
        db.DateTime,
        default=utcnow_naive,
        nullable=False,
    )
    updated_at = db.Column(
        db.DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    __table_args__ = (
        db.CheckConstraint(
            "amount >= 0",
            name="ck_market_purchase_expense_amount_non_negative",
        ),
        db.CheckConstraint(
            "expense_type in ('transport','documentation','broker','accommodation','meals','miscellaneous','loading','offloading','labour','permit','fuel','other')",
            name="ck_market_purchase_expense_type",
        ),
        db.Index(
            "ix_market_purchase_expense_batch_purchase_type",
            "aggregation_batch_id",
            "market_purchase_id",
            "expense_type",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<MarketPurchaseExpense {self.id} "
            f"{self.expense_type} {self.amount} {self.currency}>"
        )