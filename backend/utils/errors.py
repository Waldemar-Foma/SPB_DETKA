from flask import jsonify


def json_error(code: str, message: str, status: int):
    return jsonify({"error": {"code": code, "message": message}}), status