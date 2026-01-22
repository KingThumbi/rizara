# app/models.py

import uuid
import enum
from datetime import datetime, date

from flask_login import UserMixin
from sqlalchemy import Enum as SAEnum

from .extensions import db


# =========================================================
# User model (Authentication + Roles)
# =========================================================
class User(UserMixin, db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(30), unique=True, nullable=True)

    password_hash = db.Column(db.String(255), nullable=False)

    # roles: super-admin/admin/staff/buyer/farmer/transporter etc (future)
    role = db.Column(db.String(30), nullable=False, default="buyer")
    is_admin = db.Column(db.Boolean, default=False)

    # ✅ Security + lifecycle
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    failed_login_attempts = db.Column(db.Integer, default=0, nullable=False)
    locked_until = db.Column(db.DateTime, nullable=True)

    must_change_password = db.Column(db.Boolean, default=False, nullable=False)
    password_changed_at = db.Column(db.DateTime, nullable=True)

    last_login_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    def __repr__(self):
        return f"<User {self.id} {self.email}>"


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
    village = db.Column(db.String(120))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    location_notes = db.Column(db.String(255))
    onboarded_at = db.Column(db.DateTime, default=datetime.utcnow)

    goats = db.relationship("Goat", backref="farmer", lazy=True, cascade="all, delete-orphan")
    sheep = db.relationship("Sheep", backref="farmer", lazy=True, cascade="all, delete-orphan")
    cattle = db.relationship("Cattle", backref="farmer", lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Farmer {self.id} {self.name}>"


# =========================================================
# Base Animal (abstract)
# =========================================================
class BaseAnimal(db.Model):
    __abstract__ = True

    id = db.Column(db.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    farmer_tag = db.Column(db.String(64), nullable=False)
    rizara_id = db.Column(db.String(64), unique=True, nullable=False)

    sex = db.Column(db.String(10))
    breed = db.Column(db.String(50))
    estimated_dob = db.Column(db.Date)

    status = db.Column(db.String(30), nullable=False, default="on_farm")

    farmer_id = db.Column(db.Integer, db.ForeignKey("farmer.id"), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # --- Operational flags ---
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # --- Aggregation snapshot (purchase point) ---
    aggregated_at = db.Column(db.DateTime)
    aggregated_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    live_weight_kg = db.Column(db.Float)
    weight_method = db.Column(db.String(20))  # scale | estimated | tape | other
    purchase_price_per_head = db.Column(db.Float)
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

    def __repr__(self):
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

    def __repr__(self):
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


    def __repr__(self):
        return f"<Cattle {self.id} {self.rizara_id} {self.status}>"


# =========================================================
# Aggregation Batch (single animal type per batch)
# =========================================================
class AggregationBatch(db.Model):
    __tablename__ = "aggregation_batch"

    id = db.Column(db.Integer, primary_key=True)
    animal_type = db.Column(db.String(20), nullable=False)  # goat, sheep, cattle
    site_name = db.Column(db.String(120), nullable=False)
    date_received = db.Column(db.Date, default=date.today)

    is_locked = db.Column(db.Boolean, default=False)
    locked_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_by = db.relationship("User", foreign_keys=[created_by_user_id], lazy="joined")

    goats = db.relationship("Goat", back_populates="aggregation_batch", lazy="select")
    sheep = db.relationship("Sheep", back_populates="aggregation_batch", lazy="select")
    cattle = db.relationship("Cattle", back_populates="aggregation_batch", lazy="select")

    def __repr__(self):
        return f"<AggregationBatch {self.id} {self.animal_type}>"


# =========================================================
# Processing association tables (many-to-many)
# =========================================================
processing_goats = db.Table(
    "processing_goats",
    db.Column("processing_batch_id", db.Integer, db.ForeignKey("processing_batch.id"), primary_key=True),
    db.Column("goat_id", db.UUID(as_uuid=True), db.ForeignKey("goat.id"), primary_key=True),
)

processing_sheep = db.Table(
    "processing_sheep",
    db.Column("processing_batch_id", db.Integer, db.ForeignKey("processing_batch.id"), primary_key=True),
    db.Column("sheep_id", db.UUID(as_uuid=True), db.ForeignKey("sheep.id"), primary_key=True),
)

processing_cattle = db.Table(
    "processing_cattle",
    db.Column("processing_batch_id", db.Integer, db.ForeignKey("processing_batch.id"), primary_key=True),
    db.Column("cattle_id", db.UUID(as_uuid=True), db.ForeignKey("cattle.id"), primary_key=True),
)


# =========================================================
# Processing Batch (single animal type per batch)
# =========================================================
class ProcessingBatch(db.Model):
    __tablename__ = "processing_batch"

    id = db.Column(db.Integer, primary_key=True)
    animal_type = db.Column(db.String(20), nullable=False)  # goat, sheep, cattle
    facility = db.Column(db.String(120), nullable=False)
    slaughter_date = db.Column(db.Date)
    halal_cert_ref = db.Column(db.String(120))

    is_locked = db.Column(db.Boolean, default=False)
    locked_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_by = db.relationship("User", foreign_keys=[created_by_user_id], lazy="joined")

    goats = db.relationship("Goat", secondary=processing_goats, back_populates="processing_batches")
    sheep = db.relationship("Sheep", secondary=processing_sheep, back_populates="processing_batches")
    cattle = db.relationship("Cattle", secondary=processing_cattle, back_populates="processing_batches")

    def __repr__(self):
        return f"<ProcessingBatch {self.id} {self.animal_type}>"


# =========================================================
# Traceability Records
# =========================================================
class TraceabilityRecord(db.Model):
    __tablename__ = "traceability_record"

    id = db.Column(db.Integer, primary_key=True)
    animal_type = db.Column(db.String(20), nullable=False)  # goat, sheep, cattle
    animal_id = db.Column(db.UUID(as_uuid=True), nullable=False)
    qr_code_data = db.Column(db.Text, nullable=False)
    public_url = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# =========================================================
# ContactMessage
# =========================================================
class ContactMessage(db.Model):
    __tablename__ = "contact_messages"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(200))
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="new")  # new, reviewed, closed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# =========================================================
# Buyer (Business profile) + optional login link
# =========================================================
class Buyer(db.Model):
    __tablename__ = "buyer"

    id = db.Column(db.Integer, primary_key=True)

    # Optional: link this Buyer to a login user account
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=True)
    user = db.relationship("User", foreign_keys=[user_id], lazy="joined")

    name = db.Column(db.String(160), nullable=False)
    phone = db.Column(db.String(30))
    email = db.Column(db.String(120))
    address = db.Column(db.String(255))
    tax_pin = db.Column(db.String(60))

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Buyer {self.id} {self.name}>"


# =========================================================
# OrderRequest (PUBLIC + Buyer Portal repeat orders)
# =========================================================
class OrderRequest(db.Model):
    __tablename__ = "order_requests"

    id = db.Column(db.Integer, primary_key=True)

    # Optional: if order came from a logged-in buyer
    buyer_id = db.Column(db.Integer, db.ForeignKey("buyer.id"), nullable=True)
    buyer = db.relationship("Buyer", foreign_keys=[buyer_id], lazy="joined")

    buyer_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(120))
    product = db.Column(db.String(120), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    delivery_location = db.Column(db.String(200), nullable=False)
    notes = db.Column(db.Text)

    status = db.Column(db.String(20), default="new")  # new, reviewed, approved, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# =========================================================
# AnimalEvent (generic)
# =========================================================
class AnimalEvent(db.Model):
    __tablename__ = "animal_event"

    id = db.Column(db.Integer, primary_key=True)

    animal_type = db.Column(db.String(20), nullable=False)  # goat, sheep, cattle
    animal_id = db.Column(db.UUID(as_uuid=True), nullable=False)

    event_type = db.Column(db.String(50), nullable=False)
    event_datetime = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    performed_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    from_farmer_id = db.Column(db.Integer, db.ForeignKey("farmer.id"))
    to_farmer_id = db.Column(db.Integer, db.ForeignKey("farmer.id"))

    from_location = db.Column(db.String(120))
    to_location = db.Column(db.String(120))

    notes = db.Column(db.Text)
    attachment_url = db.Column(db.String(255))

    is_verified = db.Column(db.Boolean, default=True, nullable=False)
    verified_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    verified_at = db.Column(db.DateTime)


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
    paid_to = db.Column(db.String(120))
    reference = db.Column(db.String(120))
    notes = db.Column(db.Text)

    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


# =========================================================
# AnimalHealthEvent
# =========================================================
class AnimalHealthEvent(db.Model):
    __tablename__ = "animal_health_event"

    id = db.Column(db.Integer, primary_key=True)

    animal_type = db.Column(db.String(20), nullable=False)
    animal_id = db.Column(db.UUID(as_uuid=True), nullable=False)

    aggregation_batch_id = db.Column(db.Integer, db.ForeignKey("aggregation_batch.id"), nullable=False)

    diagnosis = db.Column(db.String(200))
    treatment = db.Column(db.String(200))

    cost = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(10), default="KES")

    treated_by = db.Column(db.String(120))
    event_date = db.Column(db.Date, default=date.today, nullable=False)
    notes = db.Column(db.Text)

    recorded_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


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
    parts_notes = db.Column(db.Text)

    recorded_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


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

    notes = db.Column(db.Text)

    recorded_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    recorded_by = db.relationship("User", foreign_keys=[recorded_by_user_id], lazy="joined")

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


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

    buyer_id = db.Column(db.Integer, db.ForeignKey("buyer.id"), nullable=False)
    buyer = db.relationship("Buyer", foreign_keys=[buyer_id], lazy="joined")

    processing_batch_sale_id = db.Column(
        db.Integer,
        db.ForeignKey("processing_batch_sale.id"),
        unique=True,
        nullable=False,
    )
    sale = db.relationship("ProcessingBatchSale", foreign_keys=[processing_batch_sale_id], lazy="joined")

    issue_date = db.Column(db.Date, default=date.today, nullable=False)
    due_date = db.Column(db.Date)

    status = db.Column(
        SAEnum(
            InvoiceStatus,
            name="invoice_status",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
            native_enum=False,  # uses CHECK constraint (portable & safe)
        ),
        nullable=False,
        default=InvoiceStatus.ISSUED,
    )

    # Lifecycle timestamps
    issued_at = db.Column(db.DateTime, nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    voided_at = db.Column(db.DateTime, nullable=True)

    subtotal = db.Column(db.Float, default=0.0, nullable=False)
    tax = db.Column(db.Float, default=0.0, nullable=False)
    total = db.Column(db.Float, default=0.0, nullable=False)

    notes = db.Column(db.Text)
    terms = db.Column(db.Text)

    issued_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    issued_by = db.relationship("User", foreign_keys=[issued_by_user_id], lazy="joined")

    items = db.relationship(
        "InvoiceItem",
        back_populates="invoice",
        cascade="all, delete-orphan",
        lazy="select",
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
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
    phone = db.Column(db.String(30))
    email = db.Column(db.String(120))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


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
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendor.id"))

    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(10), default="KES")

    payment_method = db.Column(db.String(30))  # cash/mpesa/bank
    reference = db.Column(db.String(120))
    cost_center = db.Column(db.String(120))
    notes = db.Column(db.Text)
    attachment_url = db.Column(db.String(255))

    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


# =========================================================
# Asset
# =========================================================
class Asset(db.Model):
    __tablename__ = "asset"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    asset_type = db.Column(db.String(60), nullable=False)  # vehicle, scale, equipment...
    ownership_type = db.Column(db.String(20), default="owned", nullable=False)  # owned/leased

    purchase_date = db.Column(db.Date)
    purchase_cost = db.Column(db.Float)
    currency = db.Column(db.String(10), default="KES")

    location = db.Column(db.String(120))
    status = db.Column(db.String(20), default="active", nullable=False)  # active/repair/disposed

    vendor_id = db.Column(db.Integer, db.ForeignKey("vendor.id"))
    notes = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


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

    notes = db.Column(db.Text)
    attachment_url = db.Column(db.String(255))

    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
