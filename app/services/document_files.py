# app/services/document_files.py
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from flask import current_app, render_template
from weasyprint import HTML

from app.services.document_renderer import render_export_sales_contract_pdf_bytes as _render_export_contract_pdf
from app.extensions import db
from app.models import Document


# =========================================================
# Types
# =========================================================
@dataclass(frozen=True)
class StoredFile:
    storage_key: str
    sha256: str


# =========================================================
# Storage helpers
# =========================================================
def _docs_storage_dir() -> str:
    """
    Local storage by default (safe + simple). Later you can swap to S3/MinIO/Spaces
    without changing callers.
    Priority:
      1) Flask config: DOCUMENT_SNAPSHOTS_DIR or DOCUMENT_STORAGE_DIR
      2) Env: DOCUMENT_SNAPSHOTS_DIR or DOCUMENT_STORAGE_DIR
      3) instance_path/snapshots
    """
    base = (
        current_app.config.get("DOCUMENT_SNAPSHOTS_DIR")
        or current_app.config.get("DOCUMENT_STORAGE_DIR")
        or os.getenv("DOCUMENT_SNAPSHOTS_DIR")
        or os.getenv("DOCUMENT_STORAGE_DIR")
    )
    if not base:
        base = os.path.join(current_app.instance_path, "snapshots")

    os.makedirs(base, exist_ok=True)
    return base


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def default_snapshot_storage_key(document: Document, *, prefix: str = "signed") -> str:
    """
    Example:
      documents/<doc_id>/v<version>/signed_20260221T010203Z.pdf
    """
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    return f"documents/{document.id}/v{document.version}/{prefix}_{ts}.pdf"


# =========================================================
# PDF rendering
# =========================================================

def _default_base_url() -> str:
    """
    Best-effort base_url for legacy call sites that don't pass base_url.
    Prefer PUBLIC_BASE_URL if configured; otherwise fallback.
    """
    cfg = (current_app.config.get("PUBLIC_BASE_URL") or "").strip() if current_app else ""
    if cfg:
        return cfg.rstrip("/")
    # Safe fallback for PDF rendering (works locally; in production set PUBLIC_BASE_URL)
    return "http://127.0.0.1:5000"


def render_export_sales_contract_pdf_bytes(document: Document, base_url: str | None = None) -> bytes:
    """
    Backward compatible wrapper.
    Canonical renderer lives in app/services/document_renderer.py and requires base_url.
    """
    return _render_export_contract_pdf(document, base_url=(base_url or _default_base_url()))

# =========================================================
# Snapshot store/load
# =========================================================
def store_document_pdf_snapshot(
    document: Document,
    *,
    pdf_bytes: bytes,
    storage_key: Optional[str] = None,
    commit: bool = False,
) -> StoredFile:
    """
    Stores an immutable PDF snapshot and writes:
      - document.storage_key
      - document.file_sha256

    IMPORTANT:
    - Call this only at an "immutable" milestone (e.g. buyer_signed, executed).
    - Default behavior does NOT commit. Caller controls transaction boundaries.
      Use commit=True only if you explicitly want this function to commit.

    Returns StoredFile(storage_key, sha256).
    """
    key = storage_key or default_snapshot_storage_key(document, prefix="signed")
    digest = sha256_hex(pdf_bytes)

    base = _docs_storage_dir()
    abs_path = os.path.join(base, key)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)

    with open(abs_path, "wb") as f:
        f.write(pdf_bytes)

    document.storage_key = key
    document.file_sha256 = digest
    db.session.add(document)

    if commit:
        db.session.commit()

    return StoredFile(storage_key=key, sha256=digest)


def load_document_snapshot_bytes(storage_key: str) -> bytes:
    base = _docs_storage_dir()
    abs_path = os.path.join(base, storage_key)
    with open(abs_path, "rb") as f:
        return f.read()