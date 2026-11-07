from __future__ import annotations

import json
import sqlite3
import threading
import urllib.error
from contextlib import closing
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from data.build_trials_db import init_db, sync_database

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "clinical_trials.db"
MAX_LIMIT = 100_000
sync_lock = threading.Lock()


class TrialHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/trials":
            try:
                self.handle_trials_api(parsed.query)
            except sqlite3.Error:
                self.send_json(500, {"error": "The trials database could not be queried."})
            return
        super().do_GET()

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/trials/refresh":
            self.send_error(404)
            return
        if not sync_lock.acquire(blocking=False):
            self.send_json(409, {"error": "A database refresh is already running."})
            return

        try:
            result = sync_database(DB_PATH)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            self.send_json(502, {"error": f"ClinicalTrials.gov refresh failed: {error}"})
        except sqlite3.Error:
            self.send_json(500, {"error": "The trials database could not be updated."})
        else:
            self.send_json(200, result)
        finally:
            sync_lock.release()

    def handle_trials_api(self, query_string: str) -> None:
        params = parse_qs(query_string)
        keyword = (params.get("keyword", [""])[0] or "").strip().lower()
        sponsor = (params.get("sponsor", [""])[0] or "").strip().lower()
        status = (params.get("status", [""])[0] or "").strip()
        phase = (params.get("phase", [""])[0] or "").strip()
        start_date = (params.get("start_date", [""])[0] or "").strip()

        try:
            limit = int((params.get("limit", ["0"])[0] or "0").strip())
            offset = int((params.get("offset", ["0"])[0] or "0").strip())
        except ValueError:
            self.send_json(400, {"error": "limit and offset must be integers."})
            return
        if limit < 0 or limit > MAX_LIMIT or offset < 0:
            self.send_json(400, {"error": f"limit must be 0-{MAX_LIMIT} and offset cannot be negative."})
            return

        where_sql = [
            "SELECT nct_id, title, status, phase, sponsor, start_date, enrollment, conditions "
            "FROM trials WHERE 1=1"
        ]
        values: list[str | int] = []
        if keyword:
            where_sql.append(
                "AND (LOWER(title) LIKE ? OR LOWER(sponsor_lower) LIKE ? "
                "OR LOWER(nct_id) LIKE ? OR LOWER(conditions) LIKE ?)"
            )
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
        with closing(sqlite3.connect(DB_PATH)) as conn, conn:
            total_count = conn.execute(
                f"SELECT COUNT(*) FROM ({base_sql})", values
            ).fetchone()[0]
            final_sql = (
                base_sql
                + " ORDER BY CASE WHEN start_date = 'N/A' THEN 1 ELSE 0 END, "
                "start_date DESC, nct_id DESC"
            )
            query_values = list(values)
            if limit:
                final_sql += " LIMIT ? OFFSET ?"
                query_values.extend([limit, offset])
            rows = conn.execute(final_sql, query_values).fetchall()
            synced = conn.execute(
                "SELECT value FROM sync_metadata WHERE key = 'last_synced_at'"
            ).fetchone()
            last_synced_at = synced[0] if synced else conn.execute(
                "SELECT MAX(created_at) FROM trials"
            ).fetchone()[0]

        self.send_json(
            200,
            {
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
                "last_synced_at": last_synced_at,
            },
        )

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    with closing(sqlite3.connect(DB_PATH)) as conn, conn:
        init_db(conn)

    handler = partial(TrialHandler, directory=str(ROOT))
    server = ThreadingHTTPServer(("127.0.0.1", 8000), handler)
    print("Serving ctg.html and the trials database at http://127.0.0.1:8000")
    server.serve_forever()


if __name__ == "__main__":
    main()
