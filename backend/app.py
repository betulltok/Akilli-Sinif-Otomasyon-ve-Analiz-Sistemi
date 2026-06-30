from flask import Flask, jsonify, request, send_from_directory
import sqlite3
import os

# backend/app.py -> proje kökü -> database/smart_classroom.db
PROJE_KOKU = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_YOLU = os.path.join(PROJE_KOKU, "database", "smart_classroom.db")
FRONTEND_KLASORU = os.path.join(PROJE_KOKU, "frontend")

app = Flask(__name__)


def get_db():
    conn = sqlite3.connect(DB_YOLU)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def index():
    return send_from_directory(FRONTEND_KLASORU, "index.html")


# Tüm veriler (limit ve zaman aralığı filtresi ile)
@app.route("/api/data")
def get_data():
    limit = request.args.get("limit", 50, type=int)
    start_time = request.args.get("start_time", type=float)
    end_time = request.args.get("end_time", type=float)

    query = "SELECT * FROM sensor_data"
    params = []

    if start_time is not None and end_time is not None:
        query += " WHERE time >= ? AND time <= ?"
        params = [start_time, end_time]
    elif start_time is not None:
        query += " WHERE time >= ?"
        params = [start_time]
    elif end_time is not None:
        query += " WHERE time <= ?"
        params = [end_time]

    query += " ORDER BY time DESC LIMIT ?"
    params.append(limit)

    conn = get_db()
    rows = conn.execute(query, params).fetchall()
    conn.close()

    return jsonify([dict(row) for row in rows])


# En son ölçüm
@app.route("/api/data/latest")
def get_latest():
    conn = get_db()
    row = conn.execute("SELECT * FROM sensor_data ORDER BY time DESC LIMIT 1").fetchone()
    conn.close()
    return jsonify(dict(row)) if row else jsonify({"error": "veri yok"})


# Sadece CO2 verileri
@app.route("/api/co2")
def get_co2():
    limit = request.args.get("limit", 50, type=int)
    conn = get_db()
    rows = conn.execute(
        "SELECT time, co2 FROM sensor_data ORDER BY time DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


# Sadece sıcaklık verileri
@app.route("/api/temperature")
def get_temperature():
    limit = request.args.get("limit", 50, type=int)
    conn = get_db()
    rows = conn.execute(
        "SELECT time, temperature FROM sensor_data ORDER BY time DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


# Sadece enerji verileri
@app.route("/api/energy")
def get_energy():
    limit = request.args.get("limit", 50, type=int)
    conn = get_db()
    rows = conn.execute(
        "SELECT time, energy FROM sensor_data ORDER BY time DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


# Sadece kişi sayısı
@app.route("/api/occupancy")
def get_occupancy():
    limit = request.args.get("limit", 50, type=int)
    conn = get_db()
    rows = conn.execute(
        "SELECT time, people FROM sensor_data ORDER BY time DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


# Geri dönüşüm kutusu doluluk durumu
@app.route("/api/trash")
def get_trash():
    limit = request.args.get("limit", 50, type=int)
    conn = get_db()
    rows = conn.execute(
        "SELECT time, trash_count FROM sensor_data ORDER BY time DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


if __name__ == "__main__":
    app.run(debug=True)