def register_blueprints(app):
    from app.routes.health import bp as health_bp
    from app.routes.overview import bp as overview_bp
    from app.routes.targets import bp as targets_bp
    from app.routes.planner import bp as planner_bp
    from app.routes.visibility import bp as visibility_bp
    from app.routes.moon import bp as moon_bp
    from app.routes.log import bp as log_bp
    from app.routes.export import bp as export_bp
    from app.routes.generator import bp as generator_bp
    from app.routes.files import bp as files_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(overview_bp)
    app.register_blueprint(targets_bp)
    app.register_blueprint(planner_bp)
    app.register_blueprint(visibility_bp)
    app.register_blueprint(moon_bp)
    app.register_blueprint(log_bp)
    app.register_blueprint(export_bp)
    app.register_blueprint(generator_bp)
    app.register_blueprint(files_bp)
