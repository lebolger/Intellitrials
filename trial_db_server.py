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
        raw_limit = (params.get("limit", ["0"])[0] or "0").strip()
        raw_offset = (params.get("offset", ["0"])[0] or "0").strip()
        limit = int(raw_limit) if raw_limit else 0
        offset = int(raw_offset) if raw_offset else 0

        with sqlite3.connect(DB_PATH) as conn:
            where_sql = [
                "SELECT nct_id, title, status, phase, sponsor, start_date, enrollment, conditions FROM trials WHERE 1=1"
            ]
            values: list[str] = []

            if keyword:
                where_sql.append("AND (")
                where_sql.append("LOWER(title) LIKE ? OR LOWER(sponsor_lower) LIKE ? OR LOWER(nct_id) LIKE ? OR LOWER(conditions) LIKE ?")
                where_sql.append(")")
                pattern = f"%{keyword}%"
                values.extend([pattern, pattern, pattern, pattern])

            if sponsor:
                where_sql.append("AND LOWER(sponsor_lower) LIKE ?")
                values.append(f"%{sponsor}%")

            if status:
                where_sql.append("AND status = ?")
                values.append(status)

            if phase:
                where_sql.append("AND phase = ?")
                values.append(phase)

            if start_date:
                where_sql.append("AND start_date >= ?")
                values.append(start_date)

            base_sql = " ".join(where_sql)
            count_sql = f"SELECT COUNT(*) FROM ({base_sql})"
            total_count = conn.execute(count_sql, values).fetchone()[0]

            final_sql = base_sql + " ORDER BY start_date DESC, nct_id DESC"
            if limit > 0:
                final_sql += " LIMIT ? OFFSET ?"
                values.extend([limit, offset])
            rows = conn.execute(final_sql, values).fetchall()

        payload = {
            "count": total_count,
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
