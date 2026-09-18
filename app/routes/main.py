from flask import Blueprint, jsonify, render_template, request

from app.services.search_orchestrator import SearchOrchestrator
from app.services.temporary_search import TemporarySearchService


main_bp = Blueprint("main", __name__)
search_orchestrator = SearchOrchestrator(TemporarySearchService())


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

    try:
        result = search_orchestrator.search(payload.get("query"))
    except ValueError as error:
        return jsonify({"success": False, "error": str(error)}), 400

    return jsonify(result), 200
