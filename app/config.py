import os


class Config:
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql://arp:arp_dev@localhost:5432/arpsurvey"
    )
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-not-for-production")
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB upload limit
    SQLALCHEMY_TRACK_MODIFICATIONS = False
