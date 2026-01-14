import uuid
from datetime import datetime, date

from flask_login import UserMixin
from .extensions import db


# =========================================================
# User model (Admin authentication)
# =========================================================
class User(UserMixin, db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    is_admin = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# =========================================================
# Farmer model
# =========================================================
class Farmer(db.Model):
    __tablename__ = "farmer"

    id = db.Column(db.Integer, primary_key=True)

    # Identity
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)

    # Administrative location
    county = db.Column(db.String(100), nullable=False)
    ward = db.Column(db.String(100), nullable=False)

    # Physical location
    village = db.Column(db.String(120))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    location_notes = db.Column(db.String(255))

    onboarded_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    goats = db.relationship(
        "Goat",
        backref="farmer",
        lazy=True,
        cascade="all, delete-orphan"
    )


# =========================================================
# Aggregation Batch (ONE → MANY with Goat)
# =========================================================
class AggregationBatch(db.Model):
    __tablename__ = "aggregation_batch"

    id = db.Column(db.Integer, primary_key=True)

    site_name = db.Column(db.String(120), nullable=False)
    date_received = db.Column(db.Date, default=date.today)

    # Operational control
    is_locked = db.Column(db.Boolean, default=False)
    locked_at = db.Column(db.DateTime)

    goats = db.relationship(
        "Goat",
        back_populates="aggregation_batch",
        lazy="select"
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# =========================================================
# Goat model (BELONGS TO ONE AggregationBatch)
# =========================================================
class Goat(db.Model):
    __tablename__ = "goat"

    id = db.Column(
        db.UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )

    # Identification
    farmer_tag = db.Column(db.String(64), nullable=False)
    rizara_id = db.Column(db.String(64), unique=True, nullable=False)

    # Attributes
    sex = db.Column(db.String(10))
    breed = db.Column(db.String(50))
    estimated_dob = db.Column(db.Date)

    # Lifecycle status
    status = db.Column(
        db.String(30),
        nullable=False,
        default="on_farm"
    )
    # on_farm → aggregated → processed → sold

    # Ownership
    farmer_id = db.Column(
        db.Integer,
        db.ForeignKey("farmer.id"),
        nullable=False
    )

    # SINGLE aggregation batch
    aggregation_batch_id = db.Column(
        db.Integer,
        db.ForeignKey("aggregation_batch.id"),
        nullable=True
    )

    aggregation_batch = db.relationship(
        "AggregationBatch",
        back_populates="goats"
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# =========================================================
# Association table (Processing ONLY)
# =========================================================
processing_goats = db.Table(
    "processing_goats",
    db.Column(
        "processing_batch_id",
        db.Integer,
        db.ForeignKey("processing_batch.id"),
        primary_key=True
    ),
    db.Column(
        "goat_id",
        db.UUID(as_uuid=True),
        db.ForeignKey("goat.id"),
        primary_key=True
    ),
)


# =========================================================
# Processing Batch (MANY ↔ MANY with Goat)
# =========================================================
class ProcessingBatch(db.Model):
    __tablename__ = "processing_batch"

    id = db.Column(db.Integer, primary_key=True)

    facility = db.Column(db.String(120), nullable=False)
    slaughter_date = db.Column(db.Date)
    halal_cert_ref = db.Column(db.String(120))

    # Operational control
    is_locked = db.Column(db.Boolean, default=False)
    locked_at = db.Column(db.DateTime)

    goats = db.relationship(
        "Goat",
        secondary=processing_goats,
        backref="processing_batches"
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# =========================================================
# Traceability Records (QR / Public View)
# =========================================================
class TraceabilityRecord(db.Model):
    __tablename__ = "traceability_record"

    id = db.Column(db.Integer, primary_key=True)

    goat_id = db.Column(
        db.UUID(as_uuid=True),
        db.ForeignKey("goat.id"),
        nullable=False
    )

    qr_code_data = db.Column(db.Text, nullable=False)
    public_url = db.Column(db.String(255), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# =========================================================
# ContactMessage model (for Contact Us form submissions)
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
# OrderRequest model (for Place Order form submissions)
# =========================================================
class OrderRequest(db.Model):
    __tablename__ = "order_requests"

    id = db.Column(db.Integer, primary_key=True)
    buyer_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(120))
    product = db.Column(db.String(120), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    delivery_location = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), default="new")  # new, reviewed, approved, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
# =========================================================
# End of models.py
# =========================================================