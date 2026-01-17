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
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    county = db.Column(db.String(100), nullable=False)
    ward = db.Column(db.String(100), nullable=False)
    village = db.Column(db.String(120))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    location_notes = db.Column(db.String(255))
    onboarded_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships to animals
    goats = db.relationship("Goat", backref="farmer", lazy=True, cascade="all, delete-orphan")
    sheep = db.relationship("Sheep", backref="farmer", lazy=True, cascade="all, delete-orphan")
    cattle = db.relationship("Cattle", backref="farmer", lazy=True, cascade="all, delete-orphan")


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


# =========================================================
# Goat model
# =========================================================
class Goat(BaseAnimal):
    __tablename__ = "goat"

    aggregation_batch_id = db.Column(db.Integer, db.ForeignKey("aggregation_batch.id"))
    aggregation_batch = db.relationship("AggregationBatch", back_populates="goats")
    processing_batches = db.relationship(
        "ProcessingBatch",
        secondary="processing_goats",
        back_populates="goats"
    )


# =========================================================
# Sheep model
# =========================================================
class Sheep(BaseAnimal):
    __tablename__ = "sheep"

    aggregation_batch_id = db.Column(db.Integer, db.ForeignKey("aggregation_batch.id"))
    aggregation_batch = db.relationship("AggregationBatch", back_populates="sheep")
    processing_batches = db.relationship(
        "ProcessingBatch",
        secondary="processing_sheep",
        back_populates="sheep"
    )


# =========================================================
# Cattle model
# =========================================================
class Cattle(BaseAnimal):
    __tablename__ = "cattle"

    aggregation_batch_id = db.Column(db.Integer, db.ForeignKey("aggregation_batch.id"))
    aggregation_batch = db.relationship("AggregationBatch", back_populates="cattle")
    processing_batches = db.relationship(
        "ProcessingBatch",
        secondary="processing_cattle",
        back_populates="cattle"
    )


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

    # Relationships to animals
    goats = db.relationship("Goat", back_populates="aggregation_batch", lazy="select")
    sheep = db.relationship("Sheep", back_populates="aggregation_batch", lazy="select")
    cattle = db.relationship("Cattle", back_populates="aggregation_batch", lazy="select")


# =========================================================
# Processing association tables
# =========================================================
processing_goats = db.Table(
    "processing_goats",
    db.Column("processing_batch_id", db.Integer, db.ForeignKey("processing_batch.id"), primary_key=True),
    db.Column("goat_id", db.UUID(as_uuid=True), db.ForeignKey("goat.id"), primary_key=True)
)

processing_sheep = db.Table(
    "processing_sheep",
    db.Column("processing_batch_id", db.Integer, db.ForeignKey("processing_batch.id"), primary_key=True),
    db.Column("sheep_id", db.UUID(as_uuid=True), db.ForeignKey("sheep.id"), primary_key=True)
)

processing_cattle = db.Table(
    "processing_cattle",
    db.Column("processing_batch_id", db.Integer, db.ForeignKey("processing_batch.id"), primary_key=True),
    db.Column("cattle_id", db.UUID(as_uuid=True), db.ForeignKey("cattle.id"), primary_key=True)
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

    # Relationships to animals
    goats = db.relationship("Goat", secondary=processing_goats, back_populates="processing_batches")
    sheep = db.relationship("Sheep", secondary=processing_sheep, back_populates="processing_batches")
    cattle = db.relationship("Cattle", secondary=processing_cattle, back_populates="processing_batches")


# =========================================================
# Traceability Records (extendable to all animals)
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
# ContactMessage model
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
# OrderRequest model
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
    notes = db.Column(db.Text)  # optional notes
    status = db.Column(db.String(20), default="new")  # new, reviewed, approved, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
