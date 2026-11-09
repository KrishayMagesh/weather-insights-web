"""Weather Insights: log in, compare the weather of two cities, and train next-day
temperature models for any city. Everything you create is saved to your account."""
import io
import json

from flask import Flask, abort, flash, g, redirect, render_template, request, send_file, url_for

import compare_core
import predict_core
import weather_api
from auth_db import configure, get_db, login_required, now

SCHEMA = """
CREATE TABLE IF NOT EXISTS comparisons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    city_a TEXT NOT NULL,
    city_b TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    table_json TEXT NOT NULL,
    takeaways_json TEXT NOT NULL,
    temp_png BLOB NOT NULL,
    rain_png BLOB NOT NULL,
    data_csv BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    city TEXT NOT NULL,
    years INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    best_model TEXT NOT NULL,
    best_mae REAL NOT NULL,
    baseline_mae REAL NOT NULL,
    summary_json TEXT NOT NULL,
    predictions_png BLOB NOT NULL,
    importance_png BLOB NOT NULL
);
"""
COMPARE_YEARS = [1, 2, 3, 5]
PREDICT_YEARS = [2, 3, 5]
CHARTS = {"comparisons": {"temperature": "temp_png", "rainfall": "rain_png"},
          "runs": {"predictions": "predictions_png", "importance": "importance_png"}}


def read_years(allowed, default):
    try:
        years = int(request.form.get("years", default))
    except ValueError:
        return None
    return years if years in allowed else None


def create_app(test_config=None):
    app = Flask(__name__)
    app.config["APP_NAME"] = "Weather Insights"
    configure(app, test_config, SCHEMA)

    def owned(table, item_id, columns="*"):
        row = get_db(app).execute(f"SELECT {columns} FROM {table} WHERE id = ? AND user_id = ?",
                                  (item_id, g.user["id"])).fetchone()
        if row is None:
            abort(404)
        return row

    def delete_owned(table, item_id, message):
        owned(table, item_id, "id")
        db = get_db(app)
        db.execute(f"DELETE FROM {table} WHERE id = ? AND user_id = ?", (item_id, g.user["id"]))
        db.commit()
        flash(message, "ok")
        return redirect(url_for("dashboard"))

    def chart_response(table, item_id, chart):
        column = CHARTS[table].get(chart)
        if column is None:
            abort(404)
        return app.response_class(owned(table, item_id, column)[column], mimetype="image/png")

    @app.get("/dashboard")
    @login_required
    def dashboard():
        db = get_db(app)
        comparisons = db.execute(
            "SELECT id, city_a, city_b, start_date, end_date, created_at FROM comparisons "
            "WHERE user_id = ? ORDER BY id DESC", (g.user["id"],)).fetchall()
        runs = db.execute(
            "SELECT id, city, years, created_at, best_model, best_mae, baseline_mae FROM runs "
            "WHERE user_id = ? ORDER BY id DESC", (g.user["id"],)).fetchall()
        return render_template("dashboard.html", comparisons=comparisons, runs=runs,
                               compare_years=COMPARE_YEARS, predict_years=PREDICT_YEARS)

    # ---------- compare two cities ----------
    @app.post("/compare")
    @login_required
    def compare():
        years = read_years(COMPARE_YEARS, "2")
        if years is None:
            flash("Please choose a valid time range.", "error")
            return redirect(url_for("dashboard"))
        try:
            place_a = weather_api.geocode(request.form.get("city_a"))
            place_b = weather_api.geocode(request.form.get("city_b"))
            if place_a["label"] == place_b["label"]:
                flash("Please choose two different cities.", "error")
                return redirect(url_for("dashboard"))
            start, end = weather_api.date_range(years)
            frames = {p["label"]: weather_api.fetch_daily(p["latitude"], p["longitude"], start, end)
                      for p in (place_a, place_b)}
        except weather_api.WeatherAPIError as exc:
            flash(str(exc), "error")
            return redirect(url_for("dashboard"))

        table = compare_core.comparison_table(frames)
        db = get_db(app)
        cur = db.execute(
            "INSERT INTO comparisons (user_id, city_a, city_b, start_date, end_date, created_at, "
            "table_json, takeaways_json, temp_png, rain_png, data_csv) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (g.user["id"], place_a["label"], place_b["label"], start.isoformat(), end.isoformat(),
             now(), json.dumps(table), json.dumps(compare_core.takeaways(table)),
             compare_core.temperature_chart(frames), compare_core.rainfall_chart(frames),
             compare_core.combined_csv(frames)))
        db.commit()
        return redirect(url_for("comparison", cid=cur.lastrowid))

    @app.get("/comparisons/<int:cid>")
    @login_required
    def comparison(cid):
        row = owned("comparisons", cid, "id, city_a, city_b, start_date, end_date, created_at, "
                                        "table_json, takeaways_json")
        return render_template("comparison.html", c=row, table=json.loads(row["table_json"]),
                               takeaways=json.loads(row["takeaways_json"]),
                               metrics=compare_core.METRICS)

    @app.get("/comparisons/<int:cid>/<chart>.png")
    @login_required
    def chart(cid, chart):
        return chart_response("comparisons", cid, chart)

    @app.get("/comparisons/<int:cid>/data.csv")
    @login_required
    def download(cid):
        return send_file(io.BytesIO(owned("comparisons", cid, "data_csv")["data_csv"]),
                         as_attachment=True, download_name=f"weather_comparison_{cid}.csv",
                         mimetype="text/csv")

    @app.post("/comparisons/<int:cid>/delete")
    @login_required
    def delete(cid):
        return delete_owned("comparisons", cid, "Comparison deleted.")

    # ---------- next-day temperature prediction ----------
    @app.post("/predict")
    @login_required
    def predict():
        years = read_years(PREDICT_YEARS, "3")
        if years is None:
            flash("Please choose a valid amount of history.", "error")
            return redirect(url_for("dashboard"))
        try:
            place = weather_api.geocode(request.form.get("city"))
            start, end = weather_api.date_range(years)
            df = weather_api.fetch_daily(place["latitude"], place["longitude"], start, end)
        except weather_api.WeatherAPIError as exc:
            flash(str(exc), "error")
            return redirect(url_for("dashboard"))

        summary, predictions_png, importance_png = predict_core.run_experiment(df)
        db = get_db(app)
        cur = db.execute(
            "INSERT INTO runs (user_id, city, years, created_at, best_model, best_mae, "
            "baseline_mae, summary_json, predictions_png, importance_png) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (g.user["id"], place["label"], years, now(), summary["best_model"],
             summary["best_mae"], summary["baseline_mae"], json.dumps(summary),
             predictions_png, importance_png))
        db.commit()
        return redirect(url_for("run", rid=cur.lastrowid))

    @app.get("/runs/<int:rid>")
    @login_required
    def run(rid):
        row = owned("runs", rid, "id, city, years, created_at, summary_json")
        return render_template("run.html", r=row, s=json.loads(row["summary_json"]))

    @app.get("/runs/<int:rid>/<chart>.png", endpoint="run_chart")
    @login_required
    def run_chart(rid, chart):
        return chart_response("runs", rid, chart)

    @app.post("/runs/<int:rid>/delete", endpoint="run_delete")
    @login_required
    def run_delete(rid):
        return delete_owned("runs", rid, "Prediction run deleted.")

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
