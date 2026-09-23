from flask import Blueprint, current_app, jsonify, render_template, request


main_bp = Blueprint("main", __name__)


@main_bp.get("/")
def index():
    return render_template("index.html")


@main_bp.post("/api/search")
def search():
    if not request.is_json:
        return jsonify({"success": False, "error": "Request body must be valid JSON."}), 400

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"success": False, "error": "Request body must be a JSON object."}), 400

    result = current_app.extensions["search_orchestrator"].search(payload.get("query"))
    if not result["success"]:
        status_code = {
            "rate_limited": 429,
            "provider_unavailable": 502,
        }.get(result.get("status"), 400)
        return jsonify(result), status_code

    return jsonify(result), 200


@main_bp.post("/api/question")
def question():
    if not request.is_json:
        return jsonify({"success": False, "error": "Request body must be valid JSON."}), 400

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"success": False, "error": "Request body must be a JSON object."}), 400

    result = current_app.extensions["search_orchestrator"].answer_question(
        payload.get("question"),
        payload.get("query"),
    )
    return jsonify(result), 200 if result["success"] else 400
