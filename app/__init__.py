from flask import Flask
from .routes import bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
    app.register_blueprint(bp)

    @app.after_request
    def add_no_cache_headers(response):
        if response.mimetype in {"text/html", "text/css", "text/javascript", "application/javascript"}:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
        return response

    return app
