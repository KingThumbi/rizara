# app/config/__init__.py
from __future__ import annotations

"""
app.config is now a PACKAGE.

- Company identity lives in: app.config.company
- App runtime settings live in: app.settings (formerly app/config.py)
"""

from .company import company_context

__all__ = ["company_context"]