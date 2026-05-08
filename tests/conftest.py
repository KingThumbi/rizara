from __future__ import annotations

import pytest
from flask import Flask


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config.update(SECRET_KEY="test-secret", TESTING=True)
    return app
