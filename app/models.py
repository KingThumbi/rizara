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


class PipelineStage(enum.Enum):
    SOURCING = "sourcing"
    PROCESSING = "processing"
    COMMERCIAL = "commercial"
    SALE = "sale"
    INVOICING = "invoicing"
    PAYMENT = "payment"
    FULFILLMENT = "fulfillment"
    CLOSURE = "closure"
    EXCEPTION = "exception"


class PipelineStatus(enum.Enum):
    DRAFT = "draft"
    SOURCING = "sourcing"
    PROCESSING = "processing"
    COMMERCIAL_PENDING = "commercial_pending"
    AWAITING_SIGNATURE = "awaiting_signature"
    AWAITING_AUTHORIZATION = "awaiting_authorization"
    AUTHORIZED_FOR_PROCESSING = "authorized_for_processing"
    SALE_READY = "sale_ready"
    SALE_CREATED = "sale_created"
    AWAITING_INVOICE = "awaiting_invoice"
    INVOICED = "invoiced"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    IN_DELIVERY = "in_delivery"
    COMPLETED = "completed"
    CLOSED = "closed"
    ON_HOLD = "on_hold"
    EXCEPTION = "exception"


class AuthorizationStatus(enum.Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    SATISFIED = "satisfied"
    BLOCKED = "blocked"


class PipelinePaymentStatus(enum.Enum):
    NONE = "none"
    PENDING = "pending"
    PARTIAL = "partial"
    PAID = "paid"
    OVERDUE = "overdue"
    FAILED = "failed"
    REVERSED = "reversed"


class PipelineDeliveryStatus(enum.Enum):
    NOT_STARTED = "not_started"
    PLANNED = "planned"
    DISPATCHED = "dispatched"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    RECEIVED = "received"
    CLOSED = "closed"
    DELAYED = "delayed"
    CANCELLED = "cancelled"


class PipelineHealthStatus(enum.Enum):
    GREEN = "green"
    AMBER = "amber"
    RED = "red"
    BLUE = "blue"


class PipelineNextAction(enum.Enum):
    CAPTURE_SOURCE = "capture_source"
    START_PROCESSING = "start_processing"
    CAPTURE_YIELD = "capture_yield"
    CREATE_CONTRACT = "create_contract"
    SEND_CONTRACT = "send_contract"
    FOLLOW_UP_SIGNATURE = "follow_up_signature"
    RECORD_PREPAYMENT = "record_prepayment"
    CONFIRM_LC = "confirm_lc"
    CREATE_SALE = "create_sale"
    GENERATE_INVOICE = "generate_invoice"
    RECORD_PAYMENT = "record_payment"
    DISPATCH_DELIVERY = "dispatch_delivery"
    CONFIRM_DELIVERY = "confirm_delivery"
    CLOSE_CASE = "close_case"
    REVIEW_EXCEPTION = "review_exception"
    NONE = "none"


class PipelineEventType(enum.Enum):
    CASE_CREATED = "case_created"
    CONTRACT_LINKED = "contract_linked"
    PROCESSING_LINKED = "processing_linked"
    SALE_LINKED = "sale_linked"
    INVOICE_LINKED = "invoice_linked"
    PAYMENT_RECORDED = "payment_recorded"
    DELIVERY_UPDATED = "delivery_updated"
    STATUS_RECOMPUTED = "status_recomputed"
    CASE_CLOSED = "case_closed"

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
# Commercial Contracts / Sales Flow (clean rewrite)
# Rizara: Contract -> Contract Items/Documents -> Processing -> Sale -> Payment
# =========================================================

class Contract(db.Model):
    __tablename__ = "contracts"

    id = db.Column(db.Integer, primary_key=True)
    contract_number = db.Column(db.String(50), unique=True, nullable=False, index=True)

    buyer_id = db.Column(
        db.Integer,
        db.ForeignKey("buyer.id"),
        nullable=False,
        index=True,
    )

    contract_date = db.Column(db.Date, nullable=False)
    delivery_date = db.Column(db.Date, nullable=True)

    status = db.Column(db.String(30), nullable=False, default="draft", index=True)

    currency = db.Column(db.String(10), nullable=False, default="USD")

    price_basis = db.Column(db.String(100), nullable=True)
    payment_terms = db.Column(db.Text, nullable=True)
    delivery_terms = db.Column(db.Text, nullable=True)
    destination_country = db.Column(db.String(100), nullable=True)

    payment_security_type = db.Column(db.String(30), nullable=False, default="none")

    prepayment_required = db.Column(db.Boolean, nullable=False, default=False)
    required_prepayment_percent = db.Column(db.Numeric(8, 2), nullable=True)
    required_prepayment_amount = db.Column(db.Numeric(14, 2), nullable=True)

    lc_required = db.Column(db.Boolean, nullable=False, default=False)
    lc_number = db.Column(db.String(100), nullable=True)
    lc_issuing_bank = db.Column(db.String(150), nullable=True)
    lc_status = db.Column(db.String(30), nullable=True)

    processing_release_mode = db.Column(
        db.String(30),
        nullable=False,
        default="manual_approval",
    )

    contracted_quantity_kg = db.Column(db.Numeric(14, 2), nullable=True)
    contracted_value = db.Column(db.Numeric(14, 2), nullable=True)

    product_type = db.Column(db.String(120), nullable=True)
    quality_spec = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    submitted_for_review_at = db.Column(db.DateTime, nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    signed_at = db.Column(db.DateTime, nullable=True)
    activated_at = db.Column(db.DateTime, nullable=True)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    cancel_reason = db.Column(db.Text, nullable=True)

    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    reviewed_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    approved_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=utcnow_naive)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )

    buyer = db.relationship("Buyer", foreign_keys=[buyer_id], lazy="joined")
    created_by = db.relationship("User", foreign_keys=[created_by_user_id], lazy="joined")
    reviewed_by = db.relationship("User", foreign_keys=[reviewed_by_user_id], lazy="joined")
    approved_by = db.relationship("User", foreign_keys=[approved_by_user_id], lazy="joined")

    items = db.relationship(
        "ContractItem",
        back_populates="contract",
        cascade="all, delete-orphan",
        lazy="select",
    )

    documents = db.relationship(
        "ContractDocument",
        back_populates="contract",
        cascade="all, delete-orphan",
        lazy="select",
        order_by="desc(ContractDocument.uploaded_at)",
    )

    processing_batches = db.relationship(
        "CommercialProcessingBatch",
        back_populates="contract",
        lazy="select",
    )

    sales = db.relationship(
        "Sale",
        back_populates="contract",
        lazy="select",
    )

    @property
    def primary_document(self):
        return next((doc for doc in self.documents if doc.is_primary), None)

    @property
    def primary_signed_document(self):
        return next(
            (
                doc for doc in self.documents
                if doc.is_primary and doc.status == "signed"
            ),
            None,
        )

    @property
    def has_signed_document(self) -> bool:
        return any(doc.status == "signed" for doc in self.documents)

    @property
    def can_activate(self) -> bool:
        return (
            self.status in {"approved", "signed"}
            and self.primary_signed_document is not None
        )

    def mark_submitted(self):
        self.status = "submitted"
        self.submitted_for_review_at = utcnow_naive()

    def mark_reviewed(self, user_id=None):
        self.status = "reviewed"
        self.reviewed_at = utcnow_naive()
        self.reviewed_by_user_id = user_id

    def mark_approved(self, user_id=None):
        self.status = "approved"
        self.approved_at = utcnow_naive()
        self.approved_by_user_id = user_id

    def mark_signed(self):
        self.status = "signed"
        self.signed_at = utcnow_naive()

    def activate(self):
        if not self.primary_signed_document:
            raise ValueError("A primary signed contract document is required before activation.")

        self.status = "active"
        self.activated_at = utcnow_naive()

    def cancel(self, reason=None):
        self.status = "cancelled"
        self.cancelled_at = utcnow_naive()
        self.cancel_reason = reason

    def __repr__(self) -> str:
        return f"<Contract {self.id} {self.contract_number} {self.status}>"    

class ContractItem(db.Model):
    __tablename__ = "contract_items"

    id = db.Column(db.Integer, primary_key=True)
    contract_id = db.Column(
        db.Integer,
        db.ForeignKey("contracts.id"),
        nullable=False,
        index=True,
    )

    product_name = db.Column(db.String(120), nullable=False)
    product_code = db.Column(db.String(50), nullable=True)
    unit_of_measure = db.Column(db.String(20), nullable=False, default="kg")

    quantity = db.Column(db.Numeric(14, 2), nullable=False)
    unit_price = db.Column(db.Numeric(14, 2), nullable=False)
    total_price = db.Column(db.Numeric(14, 2), nullable=False)

    quality_spec = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=utcnow_naive)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )

    contract = db.relationship("Contract", back_populates="items", lazy="joined")
    sale_items = db.relationship("SaleItem", back_populates="contract_item", lazy="select")

    def __repr__(self) -> str:
        return f"<ContractItem {self.id} {self.product_name}>"
    

class ContractDocument(db.Model):
    __tablename__ = "contract_documents"

    id = db.Column(db.Integer, primary_key=True)

    contract_id = db.Column(
        db.Integer,
        db.ForeignKey("contracts.id"),
        nullable=False,
        index=True,
    )

    buyer_id = db.Column(
        db.Integer,
        db.ForeignKey("buyer.id"),
        nullable=True,
        index=True,
    )

    document_type = db.Column(db.String(50), nullable=False, default="other")
    title = db.Column(db.String(255), nullable=False)

    status = db.Column(db.String(30), nullable=False, default="draft")
    # draft, uploaded, sent, signed, archived, cancelled

    file_path = db.Column(db.String(500), nullable=False)
    original_filename = db.Column(db.String(255), nullable=True)
    stored_filename = db.Column(db.String(255), nullable=True)
    mime_type = db.Column(db.String(120), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)

    version_no = db.Column(db.Integer, nullable=False, default=1)
    is_primary = db.Column(db.Boolean, nullable=False, default=False)

    notes = db.Column(db.Text, nullable=True)

    signed_at = db.Column(db.DateTime, nullable=True)
    signed_by_name = db.Column(db.String(255), nullable=True)
    signed_by_email = db.Column(db.String(255), nullable=True)

    uploaded_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )

    uploaded_at = db.Column(db.DateTime, nullable=False, default=utcnow_naive)

    contract = db.relationship(
        "Contract",
        back_populates="documents",
        lazy="joined",
    )

    buyer = db.relationship(
        "Buyer",
        foreign_keys=[buyer_id],
        lazy="joined",
    )

    uploaded_by = db.relationship(
        "User",
        foreign_keys=[uploaded_by_user_id],
        lazy="joined",
    )

    def mark_signed(self, signed_by_name=None, signed_by_email=None):
        self.status = "signed"
        self.signed_at = utcnow_naive()
        self.signed_by_name = signed_by_name
        self.signed_by_email = signed_by_email

    def __repr__(self) -> str:
        return f"<ContractDocument {self.id} {self.document_type} {self.title}>"
        
processing_batch_aggregation_batches = db.Table(
    "processing_batch_aggregation_batches",
    db.Column(
        "processing_batch_id",
        db.Integer,
        db.ForeignKey("commercial_processing_batches.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "aggregation_batch_id",
        db.Integer,
        db.ForeignKey("aggregation_batch.id", ondelete="RESTRICT"),
        primary_key=True,
    ),
)

class CommercialProcessingBatch(db.Model):
    __tablename__ = "commercial_processing_batches"

    id = db.Column(db.Integer, primary_key=True)
    batch_number = db.Column(db.String(50), nullable=False, unique=True, index=True)

    contract_id = db.Column(
        db.Integer,
        db.ForeignKey("contracts.id"),
        nullable=False,
        index=True,
    )

    status = db.Column(db.String(30), nullable=False, default="draft", index=True)
    processing_date = db.Column(db.Date, nullable=True)

    source_type = db.Column(db.String(30), nullable=True)
    source_reference_id = db.Column(db.Integer, nullable=True)

    planned_input_qty = db.Column(db.Numeric(14, 2), nullable=True)
    actual_input_qty = db.Column(db.Numeric(14, 2), nullable=True)
    output_qty = db.Column(db.Numeric(14, 2), nullable=True)
    yield_percentage = db.Column(db.Numeric(8, 2), nullable=True)

    processing_authorized = db.Column(db.Boolean, nullable=False, default=False)
    authorization_status = db.Column(db.String(30), nullable=False, default="pending")
    authorization_basis = db.Column(db.String(30), nullable=True)
    authorization_note = db.Column(db.Text, nullable=True)
    authorized_at = db.Column(db.DateTime, nullable=True)

    notes = db.Column(db.Text, nullable=True)

    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )

    created_at = db.Column(db.DateTime, nullable=False, default=utcnow_naive)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )

    contract = db.relationship("Contract", back_populates="processing_batches", lazy="joined")
    created_by = db.relationship("User", foreign_keys=[created_by_user_id], lazy="joined")

    outputs = db.relationship(
        "ProcessingBatchOutput",
        back_populates="processing_batch",
        cascade="all, delete-orphan",
        lazy="select",
    )

    aggregation_batches = db.relationship(
        "AggregationBatch",
        secondary=processing_batch_aggregation_batches,
        backref=db.backref("processing_batches", lazy="dynamic"),
    )

    def __repr__(self) -> str:
        return f"<CommercialProcessingBatch {self.id} {self.batch_number}>"
    
class ProcessingBatchOutput(db.Model):
    __tablename__ = "processing_batch_outputs"

    id = db.Column(db.Integer, primary_key=True)
    processing_batch_id = db.Column(
        db.Integer,
        db.ForeignKey("commercial_processing_batches.id"),
        nullable=False,
        index=True,
    )

    product_name = db.Column(db.String(120), nullable=False)
    product_code = db.Column(db.String(50), nullable=True)
    quantity = db.Column(db.Numeric(14, 2), nullable=False)
    unit_of_measure = db.Column(db.String(20), nullable=False, default="kg")
    grade = db.Column(db.String(50), nullable=True)

    destination_type = db.Column(
        db.String(30),
        nullable=True,
        default="contract_sale",
    )

    notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=utcnow_naive)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )

    processing_batch = db.relationship(
        "CommercialProcessingBatch",
        back_populates="outputs",
        lazy="joined",
    )
    sale_items = db.relationship(
        "SaleItem",
        back_populates="processing_batch_output",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<ProcessingBatchOutput {self.id} {self.product_name}>"
    

class Sale(db.Model):
    __tablename__ = "sales"

    id = db.Column(db.Integer, primary_key=True)
    sale_number = db.Column(db.String(50), nullable=False, unique=True, index=True)

    contract_id = db.Column(
        db.Integer,
        db.ForeignKey("contracts.id"),
        nullable=False,
        index=True,
    )
    customer_id = db.Column(db.Integer, nullable=False)

    buyer_id = db.Column(
        db.Integer,
        db.ForeignKey("buyer.id"),
        nullable=False,
        index=True,
    )

    sale_date = db.Column(db.Date, nullable=False)

    invoice_type = db.Column(db.String(20), nullable=False, default="commercial")
    status = db.Column(db.String(30), nullable=False, default="draft", index=True)
    currency = db.Column(db.String(10), nullable=False, default="USD")

    subtotal = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    discount = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    tax_amount = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    total_amount = db.Column(db.Numeric(14, 2), nullable=False, default=0)

    prepaid_amount = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    amount_paid = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    balance_due = db.Column(db.Numeric(14, 2), nullable=False, default=0)

    payment_status = db.Column(
        db.String(30),
        nullable=False,
        default="unpaid",
        index=True,
    )

    processing_authorized = db.Column(db.Boolean, nullable=False, default=False)
    authorized_at = db.Column(db.DateTime, nullable=True)

    notes = db.Column(db.Text, nullable=True)

    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )

    created_at = db.Column(db.DateTime, nullable=False, default=utcnow_naive)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )

    contract = db.relationship("Contract", back_populates="sales", lazy="joined")
    buyer = db.relationship("Buyer", foreign_keys=[buyer_id], lazy="joined")
    created_by = db.relationship("User", foreign_keys=[created_by_user_id], lazy="joined")

    items = db.relationship(
        "SaleItem",
        back_populates="sale",
        cascade="all, delete-orphan",
        lazy="select",
    )

    payments = db.relationship(
        "SalePayment",
        back_populates="sale",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Sale {self.id} {self.sale_number}>"

class SaleItem(db.Model):
    __tablename__ = "sale_items"

    id = db.Column(db.Integer, primary_key=True)

    sale_id = db.Column(
        db.Integer,
        db.ForeignKey("sales.id"),
        nullable=False,
        index=True,
    )

    contract_item_id = db.Column(
        db.Integer,
        db.ForeignKey("contract_items.id"),
        nullable=True,
        index=True,
    )

    processing_batch_output_id = db.Column(
        db.Integer,
        db.ForeignKey("processing_batch_outputs.id"),
        nullable=True,
        index=True,
    )

    product_name = db.Column(db.String(120), nullable=False)
    product_code = db.Column(db.String(50), nullable=True)

    quantity = db.Column(db.Numeric(14, 2), nullable=False)
    unit_of_measure = db.Column(db.String(20), nullable=False, default="kg")

    unit_price = db.Column(db.Numeric(14, 2), nullable=False)
    line_total = db.Column(db.Numeric(14, 2), nullable=False)

    notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utcnow_naive,
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )

    sale = db.relationship(
        "Sale",
        back_populates="items",
        lazy="joined",
    )

    contract_item = db.relationship(
        "ContractItem",
        back_populates="sale_items",
        lazy="joined",
    )

    processing_batch_output = db.relationship(
        "ProcessingBatchOutput",
        back_populates="sale_items",
        lazy="joined",
    )

    def __repr__(self) -> str:
        return f"<SaleItem {self.id} {self.product_name}>"    

class SalePayment(db.Model):
    __tablename__ = "sale_payments"

    id = db.Column(db.Integer, primary_key=True)

    sale_id = db.Column(
        db.Integer,
        db.ForeignKey("sales.id"),
        nullable=False,
        index=True,
    )

    payment_date = db.Column(db.Date, nullable=False)

    # Example values:
    # payment_type: prepayment, partial_payment, final_payment, lc_settlement
    payment_type = db.Column(db.String(30), nullable=False)

    # Example values:
    # payment_method: bank_transfer, swift, cash, cheque, mpesa
    payment_method = db.Column(db.String(30), nullable=True)

    amount = db.Column(db.Numeric(14, 2), nullable=False)
    reference_number = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=True,
    )

    created_at = db.Column(db.DateTime, nullable=False, default=utcnow_naive)

    sale = db.relationship("Sale", back_populates="payments", lazy="joined")
    created_by = db.relationship("User", foreign_keys=[created_by_user_id], lazy="joined")

    def __repr__(self) -> str:
        return f"<SalePayment {self.id} {self.payment_type} {self.amount}>"


# =========================================================
# Documents (LOI, Proforma, Commercial, Packing List) + Signatures
# =========================================================
class Document(db.Model):
    __tablename__ = "document"

    # -----------------------------------------------------
    # Primary Identity
    # -----------------------------------------------------
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # -----------------------------------------------------
    # Core Relationships
    # -----------------------------------------------------
    buyer_id = db.Column(
        db.Integer,
        db.ForeignKey("buyer.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    buyer = db.relationship("Buyer", foreign_keys=[buyer_id], lazy="joined")

    # 🔥 NEW: Link document to Sale (CRITICAL for Packing List & Invoice)
    sale_id = db.Column(
        db.Integer,
        db.ForeignKey("sales.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sale = db.relationship("Sale", lazy="joined")

    # -----------------------------------------------------
    # Document Classification
    # -----------------------------------------------------
    doc_type = db.Column(db.String(50), nullable=False, index=True)
    # examples: loi, proforma_invoice, commercial_invoice, packing_list

    title = db.Column(db.String(200), nullable=False)

    status = db.Column(
        db.String(30),
        nullable=False,
        default="draft",
        index=True,
    )
    # draft → issued → signed → completed

    version = db.Column(db.Integer, nullable=False, default=1)

    # -----------------------------------------------------
    # File / Storage
    # -----------------------------------------------------
    storage_key = db.Column(db.String(500), nullable=True)
    file_sha256 = db.Column(db.String(64), nullable=True)

    # JSON payload for flexible document data
    payload = db.Column(
        MutableDict.as_mutable(JSONB),
        nullable=True,
    )

    # -----------------------------------------------------
    # Lifecycle Dates
    # -----------------------------------------------------
    issued_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)

    # -----------------------------------------------------
    # Ownership / Audit
    # -----------------------------------------------------
    created_by_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by = db.relationship("User", foreign_keys=[created_by_user_id], lazy="joined")

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=sa.text("now()"),
    )

    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=sa.text("now()"),
        onupdate=utcnow_naive,
    )

    # -----------------------------------------------------
    # Buyer Digital Signature
    # -----------------------------------------------------
    buyer_sign_token = db.Column(
        db.String(128),
        nullable=True,
        index=True,
    )

    buyer_sign_token_expires_at = db.Column(db.DateTime, nullable=True)

    buyer_signed_at = db.Column(db.DateTime, nullable=True)
    buyer_sign_name = db.Column(db.String(160), nullable=True)
    buyer_sign_email = db.Column(db.String(120), nullable=True)

    buyer_sign_ip = db.Column(db.String(64), nullable=True)
    buyer_sign_user_agent = db.Column(db.String(255), nullable=True)

    # -----------------------------------------------------
    # Token Helpers
    # -----------------------------------------------------
    def new_sign_token(self, hours: int = 72) -> str:
        token = secrets.token_urlsafe(32)
        self.buyer_sign_token = token
        self.buyer_sign_token_expires_at = utcnow_naive() + timedelta(hours=hours)
        return token

    def is_sign_token_valid(self) -> bool:
        if not self.buyer_sign_token or not self.buyer_sign_token_expires_at:
            return False
        return utcnow_naive() <= self.buyer_sign_token_expires_at

    # -----------------------------------------------------
    # Constraints & Indexes
    # -----------------------------------------------------
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

    # -----------------------------------------------------
    # Relationships
    # -----------------------------------------------------
    signatures = db.relationship(
        "DocumentSignature",
        back_populates="document",
        lazy="select",
        cascade="all, delete-orphan",
    )

    # -----------------------------------------------------
    # Debug / Logging
    # -----------------------------------------------------
    def __repr__(self) -> str:
        return (
            f"<Document id={self.id} "
            f"type={self.doc_type} "
            f"v={self.version} "
            f"status={self.status}>"
        )

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
CREATABLE_DOC_TYPES = {
    "loi": "Letter of Intent (LOI)",
    "proforma_invoice": "Proforma Invoice",
    "commercial_invoice": "Commercial Invoice",
    "packing_list": "Packing List",
}

UPLOAD_ONLY_DOC_TYPES = {
    "purchase_order": "Purchase Order",
    "letter_of_credit": "Letter of Credit (LC)",
    "health_certificate": "Health Certificate",
    "certificate_of_origin": "Certificate of Origin",
    "export_permit": "Export Permit",
    "payment_confirmation": "Payment Confirmation",
    "other": "Other Supporting Document",
}

DOCUMENT_TYPES = {
    **CREATABLE_DOC_TYPES,
    **UPLOAD_ONLY_DOC_TYPES,
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

    farmer_tag = db.Column(db.String(64), nullable=True)
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

    aggregation_batch_id = db.Column(
        db.Integer,
        db.ForeignKey("aggregation_batch.id"),
        nullable=True,
    )
    aggregation_batch = db.relationship(
        "AggregationBatch",
        back_populates="goats",
    )

    procurement_record_id = db.Column(
        db.Integer,
        db.ForeignKey("procurement_records.id"),
        nullable=True,
        index=True,
    )

    source_type = db.Column(db.String(20), nullable=True)  # farmer, market
    source_name = db.Column(db.String(160), nullable=True)

    procurement_record = db.relationship(
        "ProcurementRecord",
        primaryjoin="Goat.procurement_record_id == ProcurementRecord.id",
        foreign_keys=[procurement_record_id],
        lazy="joined",
    )

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

    aggregation_batch_id = db.Column(
        db.Integer,
        db.ForeignKey("aggregation_batch.id"),
        nullable=True,
    )
    aggregation_batch = db.relationship(
        "AggregationBatch",
        back_populates="sheep",
    )

    procurement_record_id = db.Column(
        db.Integer,
        db.ForeignKey("procurement_records.id"),
        nullable=True,
        index=True,
    )

    source_type = db.Column(db.String(20), nullable=True)  # farmer, market
    source_name = db.Column(db.String(160), nullable=True)

    procurement_record = db.relationship(
        "ProcurementRecord",
        primaryjoin="Sheep.procurement_record_id == ProcurementRecord.id",
        foreign_keys=[procurement_record_id],
        lazy="joined",
    )

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

    aggregation_batch_id = db.Column(
        db.Integer,
        db.ForeignKey("aggregation_batch.id"),
        nullable=True,
    )
    aggregation_batch = db.relationship(
        "AggregationBatch",
        back_populates="cattle",
    )

    procurement_record_id = db.Column(
        db.Integer,
        db.ForeignKey("procurement_records.id"),
        nullable=True,
        index=True,
    )

    source_type = db.Column(db.String(20), nullable=True)  # farmer, market
    source_name = db.Column(db.String(160), nullable=True)

    procurement_record = db.relationship(
        "ProcurementRecord",
        primaryjoin="Cattle.procurement_record_id == ProcurementRecord.id",
        foreign_keys=[procurement_record_id],
        lazy="joined",
    )

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
    # =====================================================
    # PROCUREMENT (UNIFIED: FARMERS + MARKETS)
    # =====================================================
    procurement_records = db.relationship(
        "ProcurementRecord",
        backref="aggregation_batch",
        lazy="select",
    )

    # =====================================================
    # FARM ANIMALS (PRIMARY SUPPLY)
    # =====================================================
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

    # =====================================================
    # PROCUREMENT (UNIFIED: FARMERS + MARKETS)
    # =====================================================
    procurement_records = db.relationship(
        "ProcurementRecord",
        backref="aggregation_batch",
        lazy="select",
        cascade="all, delete-orphan",
    )

    # =====================================================
    # LEGACY MARKET PURCHASES (TRANSITIONAL)
    # =====================================================
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

    # =====================================================
    # CONSTRAINTS
    # =====================================================
    __table_args__ = (
        db.CheckConstraint(
            "animal_type in ('goat','sheep','cattle')",
            name="ck_aggregation_batch_animal_type",
        ),
    )

    # =====================================================
    # HEADCOUNT LOGIC
    # =====================================================
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
    def procurement_headcount(self) -> int:
        return sum((r.quantity or 0) for r in self.procurement_records)

    @property
    def total_headcount(self) -> int:
        return self.farm_headcount + self.procurement_headcount

    # =====================================================
    # COST LOGIC (PROCUREMENT-DRIVEN)
    # =====================================================
    @property
    def procurement_cost_total(self) -> float:
        return float(sum((r.total_cost or 0.0) for r in self.procurement_records))

    @property
    def estimated_procurement_weight_kg(self) -> float:
        return float(sum((r.estimated_total_weight_kg or 0.0) for r in self.procurement_records))

    # =====================================================
    # LEGACY MARKET (OPTIONAL / TRANSITION)
    # =====================================================
    @property
    def market_headcount(self) -> int:
        return sum((purchase.total_headcount or 0) for purchase in self.market_purchases)

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

    # =====================================================
    # DEBUG
    # =====================================================
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
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    OVERDUE = "overdue"
    VOID = "void"


# =========================================================
# Invoice
# References Contract Document + sells from InventoryLot via InvoiceItem
# =========================================================
class Invoice(db.Model):
    __tablename__ = "invoice"

    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(40), unique=True, nullable=False, index=True)

    buyer_id = db.Column(
        db.Integer,
        db.ForeignKey("buyer.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    contract_document_id = db.Column(
        db.Integer,
        db.ForeignKey("contract_documents.id"),
        nullable=True,
        index=True,
    )

    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"), nullable=True, index=True)
    contract_id = db.Column(db.Integer, db.ForeignKey("contracts.id"), nullable=True, index=True)

    commercial_processing_batch_id = db.Column(
        db.Integer,
        db.ForeignKey("commercial_processing_batches.id"),
        nullable=True,
        index=True,
    )

    processing_batch_sale_id = db.Column(
        db.Integer,
        db.ForeignKey("processing_batch_sale.id"),
        unique=True,
        nullable=True,
        index=True,
    )

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
        index=True,
    )

    issued_at = db.Column(db.DateTime, nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    voided_at = db.Column(db.DateTime, nullable=True)

    currency = db.Column(db.String(10), nullable=False, default="USD")

    subtotal = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    tax = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    total = db.Column(db.Numeric(14, 2), nullable=False, default=0)

    deposit_paid = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    balance = db.Column(db.Numeric(14, 2), nullable=False, default=0)

    notes = db.Column(db.Text, nullable=True)
    terms = db.Column(db.Text, nullable=True)

    issued_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    created_at = db.Column(db.DateTime, default=utcnow_naive, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    buyer = db.relationship("Buyer", foreign_keys=[buyer_id], lazy="joined")

    contract_document = db.relationship(
        "ContractDocument",
        foreign_keys=[contract_document_id],
        lazy="joined",
    )

    sale = db.relationship("Sale", foreign_keys=[sale_id], lazy="joined")
    contract = db.relationship("Contract", foreign_keys=[contract_id], lazy="joined")

    commercial_processing_batch = db.relationship(
        "CommercialProcessingBatch",
        foreign_keys=[commercial_processing_batch_id],
        lazy="joined",
    )

    legacy_sale = db.relationship(
        "ProcessingBatchSale",
        foreign_keys=[processing_batch_sale_id],
        lazy="joined",
    )

    issued_by = db.relationship("User", foreign_keys=[issued_by_user_id], lazy="joined")

    items = db.relationship(
        "InvoiceItem",
        back_populates="invoice",
        cascade="all, delete-orphan",
        lazy="select",
    )

    payments = db.relationship(
        "InvoicePayment",
        back_populates="invoice",
        cascade="all, delete-orphan",
        lazy="select",
        order_by="desc(InvoicePayment.paid_at)",
    )

    @property
    def amount_paid(self):
        return self.deposit_paid or 0

    @property
    def outstanding_amount(self):
        return self.balance or 0

    def recalculate_totals(self):
        self.subtotal = sum((item.line_total or 0) for item in self.items)
        self.total = (self.subtotal or 0) + (self.tax or 0)

        total_paid = sum((payment.amount or 0) for payment in self.payments)

        if total_paid:
            self.deposit_paid = total_paid

        self.balance = (self.total or 0) - (self.deposit_paid or 0)

        if self.balance <= 0 and self.total > 0:
            self.balance = 0
            self.status = InvoiceStatus.PAID
            if not self.paid_at:
                self.paid_at = utcnow_naive()
        elif self.deposit_paid and self.deposit_paid > 0:
            self.status = InvoiceStatus.PARTIALLY_PAID
            self.paid_at = None
        else:
            self.status = InvoiceStatus.ISSUED
            self.paid_at = None

    def __repr__(self) -> str:
        return f"<Invoice {self.id} {self.invoice_number} {self.status}>"
    
# =========================================================
# Invoice Item
# Sells from InventoryLot
# =========================================================
class InvoiceItem(db.Model):
    __tablename__ = "invoice_item"

    id = db.Column(db.Integer, primary_key=True)

    invoice_id = db.Column(
        db.Integer,
        db.ForeignKey("invoice.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    inventory_lot_id = db.Column(
        db.Integer,
        db.ForeignKey("inventory_lot.id"),
        nullable=True,
        index=True,
    )

    description = db.Column(db.String(255), nullable=False)

    quantity = db.Column(db.Numeric(14, 2), nullable=False, default=1)
    unit = db.Column(db.String(20), default="kg", nullable=False)

    unit_price = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    line_total = db.Column(db.Numeric(14, 2), nullable=False, default=0)

    invoice = db.relationship(
        "Invoice",
        back_populates="items",
        lazy="joined",
    )

    inventory_lot = db.relationship(
        "InventoryLot",
        back_populates="invoice_items",
        lazy="joined",
    )

    def __repr__(self) -> str:
        return f"<InvoiceItem {self.id} {self.description} qty={self.quantity}>"

# =========================================================
# Invoice Payment
# Appended payment/receipt records for invoice settlement
# =========================================================
class InvoicePayment(db.Model):
    __tablename__ = "invoice_payments"

    id = db.Column(db.Integer, primary_key=True)

    receipt_number = db.Column(
        db.String(40),
        unique=True,
        nullable=False,
        index=True,
    )

    invoice_id = db.Column(
        db.Integer,
        db.ForeignKey("invoice.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    amount = db.Column(db.Numeric(14, 2), nullable=False)

    method = db.Column(db.String(50), nullable=True)
    reference = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    paid_at = db.Column(db.DateTime, default=utcnow_naive, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow_naive, nullable=False)

    invoice = db.relationship(
        "Invoice",
        back_populates="payments",
        lazy="joined",
    )

    def __repr__(self) -> str:
        return f"<InvoicePayment {self.receipt_number} invoice={self.invoice_id} amount={self.amount}>"
        
# =========================================================
# Unified Pipeline / Control Tower (MATCHES MIGRATION)
# =========================================================

class PipelineCase(db.Model):
    __tablename__ = "pipeline_case"

    id = db.Column(db.Integer, primary_key=True)
    case_number = db.Column(db.String(50), unique=True, nullable=False, index=True)

    buyer_id = db.Column(db.Integer, db.ForeignKey("buyer.id"), nullable=True, index=True)
    contract_id = db.Column(db.Integer, db.ForeignKey("contracts.id"), nullable=True, index=True)

    # KEEP ONLY ID (NO FK, NO RELATIONSHIP)
    commercial_processing_batch_id = db.Column(db.Integer, nullable=True, index=True)

    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"), nullable=True, index=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoice.id"), nullable=True, index=True)

    current_stage = db.Column(db.String(30), nullable=False, default="sourcing", index=True)
    current_status = db.Column(db.String(40), nullable=False, default="draft", index=True)
    authorization_status = db.Column(db.String(30), nullable=False, default="pending", index=True)
    payment_status = db.Column(db.String(30), nullable=False, default="none", index=True)
    delivery_status = db.Column(db.String(30), nullable=False, default="not_started", index=True)
    health_status = db.Column(db.String(20), nullable=False, default="green", index=True)
    next_action = db.Column(db.String(50), nullable=False, default="capture_source")

    next_action_label = db.Column(db.String(255), nullable=True)
    blocking_reason = db.Column(db.Text, nullable=True)

    output_qty = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    sold_qty = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    invoiced_amount = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    paid_amount = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    outstanding_amount = db.Column(db.Numeric(14, 2), nullable=False, default=0)

    currency = db.Column(db.String(10), nullable=True)
    is_closed = db.Column(db.Boolean, nullable=False, default=False)
    closed_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=utcnow_naive)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow_naive, onupdate=utcnow_naive)

    # SAFE RELATIONSHIPS ONLY
    buyer = db.relationship("Buyer", lazy="joined")
    contract = db.relationship("Contract", lazy="joined")
    sale = db.relationship("Sale", lazy="joined")
    invoice = db.relationship("Invoice", lazy="joined")

    events = db.relationship(
        "PipelineEvent",
        back_populates="pipeline_case",
        cascade="all, delete-orphan",
        lazy="select",
        order_by="desc(PipelineEvent.event_at)",
    )

    deliveries = db.relationship(
        "PipelineDelivery",
        back_populates="pipeline_case",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self):
        return f"<PipelineCase {self.id} {self.case_number} {self.current_status}>"


class PipelineDelivery(db.Model):
    __tablename__ = "pipeline_delivery"

    id = db.Column(db.Integer, primary_key=True)

    pipeline_case_id = db.Column(
        db.Integer,
        db.ForeignKey("pipeline_case.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"), nullable=True, index=True)

    delivery_number = db.Column(db.String(50), nullable=True, index=True)
    destination = db.Column(db.String(200), nullable=True)
    shipping_mode = db.Column(db.String(50), nullable=True)

    quantity_kg = db.Column(db.Numeric(14, 2), nullable=False, default=0)

    dispatch_date = db.Column(db.Date, nullable=True)
    delivery_date = db.Column(db.Date, nullable=True)

    # STRING (matches migration)
    status = db.Column(db.String(30), nullable=False, default="planned", index=True)

    shipping_docs_uploaded = db.Column(db.Boolean, nullable=False, default=False)
    proof_of_delivery_uploaded = db.Column(db.Boolean, nullable=False, default=False)
    notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=utcnow_naive)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow_naive, onupdate=utcnow_naive)

    pipeline_case = db.relationship("PipelineCase", back_populates="deliveries", lazy="joined")
    sale = db.relationship("Sale", foreign_keys=[sale_id], lazy="joined")

    def __repr__(self):
        return f"<PipelineDelivery {self.id} {self.delivery_number or ''} {self.status}>"



class PipelineEvent(db.Model):
    __tablename__ = "pipeline_event"

    id = db.Column(db.Integer, primary_key=True)

    pipeline_case_id = db.Column(
        db.Integer,
        db.ForeignKey("pipeline_case.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # STRING (matches migration)
    event_type = db.Column(db.String(50), nullable=False, index=True)

    message = db.Column(db.Text, nullable=True)
    metadata_json = db.Column(MutableDict.as_mutable(JSONB), nullable=True)

    actor_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)

    event_at = db.Column(db.DateTime, nullable=False, default=utcnow_naive, index=True)

    pipeline_case = db.relationship("PipelineCase", back_populates="events", lazy="joined")
    actor_user = db.relationship("User", foreign_keys=[actor_user_id], lazy="joined")

    def __repr__(self):
        return f"<PipelineEvent {self.id} {self.event_type}>"
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

# =========================================================
# ProcurementSource
# Unified source: farmers are primary, markets are supplementary
# =========================================================
class ProcurementSource(db.Model):
    __tablename__ = "procurement_sources"

    id = db.Column(db.Integer, primary_key=True)

    source_type = db.Column(db.String(20), nullable=False, index=True)
    # farmer, market

    name = db.Column(db.String(160), nullable=False, index=True)
    phone = db.Column(db.String(50), nullable=True)
    location = db.Column(db.String(160), nullable=True)
    county = db.Column(db.String(100), nullable=True)

    notes = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=utcnow_naive, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    procurement_records = db.relationship(
        "ProcurementRecord",
        back_populates="source",
        lazy="select",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        db.CheckConstraint(
            "source_type in ('farmer','market')",
            name="ck_procurement_source_type",
        ),
    )

    def __repr__(self) -> str:
        return f"<ProcurementSource {self.id} {self.source_type} {self.name}>"

# =========================================================
# ProcurementRecord
# Creates animals and attaches them to an aggregation batch
# =========================================================
class ProcurementRecord(db.Model):
    __tablename__ = "procurement_records"

    id = db.Column(db.Integer, primary_key=True)

    source_id = db.Column(
        db.Integer,
        db.ForeignKey("procurement_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    aggregation_batch_id = db.Column(
        db.Integer,
        db.ForeignKey("aggregation_batch.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    animal_type = db.Column(db.String(20), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False, default=0)

    unit_price = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_cost = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    estimated_total_weight_kg = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    estimated_avg_weight_kg = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    purchase_date = db.Column(db.Date, default=date.today, nullable=False)

    status = db.Column(db.String(30), default="draft", nullable=False, index=True)
    # draft, confirmed, received, cancelled

    reference = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=utcnow_naive, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    source = db.relationship(
        "ProcurementSource",
        back_populates="procurement_records",
        lazy="joined",
    )

    __table_args__ = (
        db.CheckConstraint(
            "animal_type in ('goat','sheep','cattle')",
            name="ck_procurement_record_animal_type",
        ),
        db.CheckConstraint(
            "quantity >= 0",
            name="ck_procurement_record_quantity_non_negative",
        ),
        db.CheckConstraint(
            "unit_price >= 0",
            name="ck_procurement_record_unit_price_non_negative",
        ),
        db.CheckConstraint(
            "total_cost >= 0",
            name="ck_procurement_record_total_cost_non_negative",
        ),
        db.CheckConstraint(
            "status in ('draft','confirmed','received','cancelled')",
            name="ck_procurement_record_status",
        ),
    )

    def generate_animals(self):
        if not self.aggregation_batch:
            raise ValueError("Procurement record must be linked to an aggregation batch.")

        if self.animal_type != self.aggregation_batch.animal_type:
            raise ValueError("Animal type does not match aggregation batch animal type.")

        if self.status == "received":
            raise ValueError("Animals have already been generated for this procurement record.")

        model_map = {
            "goat": Goat,
            "sheep": Sheep,
            "cattle": Cattle,
        }

        prefix_map = {
            "goat": "GOAT",
            "sheep": "SHEEP",
            "cattle": "CATTLE",
        }

        AnimalModel = model_map.get(self.animal_type)

        if not AnimalModel:
            raise ValueError("Unsupported animal type.")

        created = []
        year = self.purchase_date.year if self.purchase_date else date.today().year

        existing_count = AnimalModel.query.count()

        for i in range(1, (self.quantity or 0) + 1):
            sequence = existing_count + i

            animal = AnimalModel(
                rizara_id=f"RZ-{prefix_map[self.animal_type]}-{year}-P{self.id}-{sequence:04d}",
                aggregation_batch_id=self.aggregation_batch_id,
                status="aggregated",
                source_type=self.source.source_type if self.source else None,
                source_name=self.source.name if self.source else None,
                procurement_record_id=self.id,
            )

            db.session.add(animal)
            created.append(animal)

        self.status = "received"

        return created

    def __repr__(self) -> str:
        return f"<ProcurementRecord {self.id} {self.animal_type} qty={self.quantity}>"

# =========================================================
# InventoryLot
# Yield declaration becomes saleable inventory
# =========================================================
class InventoryLot(db.Model):
    __tablename__ = "inventory_lot"

    id = db.Column(db.Integer, primary_key=True)

    processing_batch_id = db.Column(
        db.Integer,
        db.ForeignKey("processing_batch.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    batch_number = db.Column(db.String(80), nullable=False, index=True)

    product_name = db.Column(db.String(160), nullable=False)
    product_type = db.Column(db.String(80), nullable=True)
    animal_type = db.Column(db.String(20), nullable=False, index=True)

    quantity_kg = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    available_kg = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    unit = db.Column(db.String(20), default="kg", nullable=False)

    status = db.Column(db.String(30), default="available", nullable=False, index=True)
    # available, partially_sold, sold_out, adjusted, expired

    created_at = db.Column(db.DateTime, default=utcnow_naive, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    processing_batch = db.relationship(
        "ProcessingBatch",
        lazy="joined",
    )

    invoice_items = db.relationship(
        "InvoiceItem",
        back_populates="inventory_lot",
        lazy="select",
    )

    __table_args__ = (
        db.CheckConstraint(
            "animal_type in ('goat','sheep','cattle')",
            name="ck_inventory_lot_animal_type",
        ),
        db.CheckConstraint(
            "quantity_kg >= 0",
            name="ck_inventory_lot_quantity_non_negative",
        ),
        db.CheckConstraint(
            "available_kg >= 0",
            name="ck_inventory_lot_available_non_negative",
        ),
        db.CheckConstraint(
            "available_kg <= quantity_kg",
            name="ck_inventory_lot_available_not_more_than_quantity",
        ),
        db.CheckConstraint(
            "status in ('available','partially_sold','sold_out','adjusted','expired')",
            name="ck_inventory_lot_status",
        ),
    )

    def deduct_stock(self, quantity):
        if quantity <= 0:
            raise ValueError("Quantity must be greater than zero.")

        if self.available_kg < quantity:
            raise ValueError("Insufficient inventory available.")

        self.available_kg -= quantity

        if self.available_kg == 0:
            self.status = "sold_out"
        elif self.available_kg < self.quantity_kg:
            self.status = "partially_sold"
        else:
            self.status = "available"

    def __repr__(self) -> str:
        return f"<InventoryLot {self.id} {self.product_name} available={self.available_kg}>"        