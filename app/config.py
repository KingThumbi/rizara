import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")

    SQLALCHEMY_DATABASE_URI = (
        os.environ.get("DATABASE_URL")
        or "postgresql+psycopg2://thumbi:1010@localhost:5432/rizara"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False
