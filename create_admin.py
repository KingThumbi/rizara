from app import create_app
from app.extensions import db
from app.models import User
from werkzeug.security import generate_password_hash

EMAIL = "admin@rizara.co.ke"
PASSWORD = "1.Dmpolin"

app = create_app()

with app.app_context():
    print("🔁 Removing existing users...")
    User.query.delete()
    db.session.commit()

    print("🔐 Creating new admin user...")

    admin = User(
        name="Rizara Super Admin",
        email=EMAIL,
        phone=None,
        role="super_admin",
        is_admin=True,
        password_hash=generate_password_hash(PASSWORD),
    )

    db.session.add(admin)
    db.session.commit()

    print("✅ Admin created:", EMAIL)
