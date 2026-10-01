from flask import Blueprint, jsonify
from backend.services.local_ai import status

bp = Blueprint("ai", __name__)

@bp.get("/status")
def ai_status():
    return jsonify({"local_only": True, **status()})
