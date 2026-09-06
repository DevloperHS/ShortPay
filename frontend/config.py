import os


class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "shortpay-local-development")
    SHORTPAY_API_URL = os.getenv("SHORTPAY_API_URL", "http://127.0.0.1:8000")
    SHORTPAY_API_TIMEOUT = float(os.getenv("SHORTPAY_API_TIMEOUT", "60"))
    SHORTPAY_INGEST_TIMEOUT = float(os.getenv("SHORTPAY_INGEST_TIMEOUT", "90"))
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
