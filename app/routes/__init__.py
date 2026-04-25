# app/routes/__init__.py
from __future__ import annotations

from flask import Blueprint

from .aggregation import aggregation_bp
from .market_purchases import market_purchase_bp
from .processing import processing_bp

# Temporary compatibility blueprint:
# keep exposing endpoints under "main" until templates are migrated
main = Blueprint("main", __name__)

def register_blueprints(app):
    app.register_blueprint(aggregation_bp)
    app.register_blueprint(market_purchase_bp)
    app.register_blueprint(processing_bp)