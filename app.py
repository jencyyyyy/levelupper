from flask import Flask, render_template, request, jsonify, Response
from scraper import get_coordinate, find_no_website
import pandas as pd
import io

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/search", methods=["POST"])
def search():
    data = request.get_json()
    location = (data.get("location") or "").strip()
    place_type = data.get("place_type", "restaurant")

    if not location:
        return jsonify({"error": "Location is required."}), 400

    coords = get_coordinate(location)
    if not coords:
        return jsonify({
            "error": "Could not find that location. Try being more specific (e.g., 'Ramankulangara, Kollam')."
        }), 400

    results = find_no_website(location=coords, radius=5000, place_type=place_type)
    results = sorted(results, key=lambda x: x["score"], reverse=True)

    return jsonify({"results": results, "count": len(results)})


@app.route("/export", methods=["POST"])
def export():
    data = request.get_json()
    results = data.get("results", [])

    if not results:
        return jsonify({"error": "No results to export."}), 400

    df = pd.DataFrame(results)
    output = io.StringIO()
    df.to_csv(output, index=False)
    output.seek(0)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"}
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
