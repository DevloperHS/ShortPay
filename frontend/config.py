import os


class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "shortpay-local-development")
    SHORTPAY_API_URL = os.getenv("SHORTPAY_API_URL", "http://127.0.0.1:8000")
    SHORTPAY_API_TIMEOUT = float(os.getenv("SHORTPAY_API_TIMEOUT", "60"))
