from flask import Blueprint, jsonify
from app import db

bp = Blueprint("health", __name__)


@bp.route("/health")
def health():
    try:
        db.session.execute(db.text("SELECT 1"))
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"status": "error", "detail": str(e)}), 503
