from flask import Flask, jsonify
import sqlite3

app = Flask(__name__)

def get_db():
    conn = sqlite3.connect("database/smart_classroom.db")
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/")
def index():
    return "Akıllı Sınıf Dijital İkizi"

@app.route("/api/data")
def get_data():
    conn = get_db()
    rows = conn.execute("SELECT * FROM sensor_data ORDER BY time DESC LIMIT 50").fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])

if __name__ == "__main__":
    app.run(debug=True)