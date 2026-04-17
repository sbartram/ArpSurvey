def register_blueprints(app):
    from app.routes.health import bp as health_bp
    from app.routes.overview import bp as overview_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(overview_bp)
