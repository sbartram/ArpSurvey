def register_blueprints(app):
    from app.routes.health import bp as health_bp
    app.register_blueprint(health_bp)
