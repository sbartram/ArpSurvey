from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def create_app(config_class=None):
    app = Flask(__name__)

    if config_class:
        app.config.from_object(config_class)
    else:
        from app.config import Config
        app.config.from_object(Config)

    db.init_app(app)

    from app.routes import register_blueprints
    register_blueprints(app)

    return app
