from __future__ import annotations

import json
import sqlite3
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "clinical_trials.db"


class TrialHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/trials":
            self.handle_trials_api(parsed.query)
            return
        super().do_GET()

    def handle_trials_api(self, query_string: str) -> None:
        params = parse_qs(query_string)
        keyword = (params.get("keyword", [""])[0] or "").strip().lower()
        sponsor = (params.get("sponsor", [""])[0] or "").strip().lower()
        status = (params.get("status", [""])[0] or "").strip()
        phase = (params.get("phase", [""])[0] or "").strip()
        start_date = (params.get("start_date", [""])[0] or "").strip()
        limit = int(params.get("limit", ["50"])[0] or 50)
        offset = int(params.get("offset", ["0"])[0] or 0)

        with sqlite3.connect(DB_PATH) as conn:
            sql = [
                "SELECT nct_id, title, status, phase, sponsor, start_date, enrollment, conditions FROM trials WHERE 1=1"
            ]
            values: list[str] = []

            if keyword:
                sql.append("AND (")
                sql.append("LOWER(title) LIKE ? OR LOWER(sponsor_lower) LIKE ? OR LOWER(nct_id) LIKE ? OR LOWER(conditions) LIKE ?")
                sql.append(")")
                pattern = f"%{keyword}%"
                values.extend([pattern, pattern, pattern, pattern])

            if sponsor:
                sql.append("AND LOWER(sponsor_lower) LIKE ?")
                values.append(f"%{sponsor}%")

            if status:
                sql.append("AND status = ?")
                values.append(status)

            if phase:
                sql.append("AND phase = ?")
                values.append(phase)

            if start_date:
                sql.append("AND start_date >= ?")
                values.append(start_date)

            sql.append("ORDER BY start_date DESC, nct_id DESC")
            sql.append("LIMIT ? OFFSET ?")
            values.extend([limit, offset])

            rows = conn.execute(" ".join(sql), values).fetchall()

        payload = {
            "count": len(rows),
            "data": [
                {
                    "nct_id": row[0],
                    "title": row[1],
                    "status": row[2],
                    "phase": row[3],
                    "sponsor": row[4],
                    "start_date": row[5],
                    "enrollment": row[6],
                    "conditions": row[7],
                }
                for row in rows
            ],
        }

        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8000), TrialHandler)
    print("Serving trials DB at http://127.0.0.1:8000")
    server.serve_forever()
