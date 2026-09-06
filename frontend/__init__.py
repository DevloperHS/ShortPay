from flask import Flask

from frontend.config import Config
from frontend.routes import dashboard
from frontend.services.shortpay_api import ShortpayAPI


def create_app(config: dict | None = None, *, api_client=None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if config:
        app.config.update(config)

    app.extensions["shortpay_api"] = api_client or ShortpayAPI(
        base_url=app.config["SHORTPAY_API_URL"],
        timeout=app.config["SHORTPAY_API_TIMEOUT"],
    )
    app.register_blueprint(dashboard)

    @app.template_filter("money")
    def format_money(cents: int | None) -> str:
        return f"${(cents or 0) / 100:,.2f}"

    return app
