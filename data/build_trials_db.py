from __future__ import annotations

import json
import sqlite3
import urllib.parse
import urllib.request
from contextlib import closing
from pathlib import Path
from typing import Callable

DB_PATH = Path(__file__).resolve().parent / "clinical_trials.db"


def fetch_page(token: str | None = None, page_size: int = 1000):
    base = "https://clinicaltrials.gov/api/v2/studies"
    params = {
        "pageSize": str(page_size),
        "query.term": "AREA[StartDate]RANGE[2020-01-01,MAX] AND AREA[OrgClass]INDUSTRY AND AREA[StudyType]INTERVENTIONAL",
    }
    if token:
        params["pageToken"] = token

    url = base + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trials (
            nct_id TEXT PRIMARY KEY,
            title TEXT,
            status TEXT,
            phase TEXT,
            sponsor TEXT,
            sponsor_lower TEXT,
            start_date TEXT,
            enrollment INTEGER,
            conditions TEXT,
            created_at TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trials_status ON trials(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trials_phase ON trials(phase)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trials_sponsor_lower ON trials(sponsor_lower)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trials_start_date ON trials(start_date)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sync_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.commit()


def normalize_study(study: dict) -> dict:
    section = study.get("protocolSection", {}) or {}
    id_module = section.get("identificationModule", {}) or {}
    status_module = section.get("statusModule", {}) or {}
    design_module = section.get("designModule", {}) or {}
    sponsor_module = section.get("sponsorCollaboratorsModule", {}) or {}
    conditions = (section.get("conditionsModule", {}) or {}).get("conditions") or []
    sponsor = sponsor_module.get("leadSponsor", {}).get("name") or "N/A"
    start_date = (status_module.get("startDateStruct") or {}).get("date") or "N/A"
    enrollment = (design_module.get("enrollmentInfo") or {}).get("count") or 0
    title = id_module.get("officialTitle") or id_module.get("briefTitle") or "No title"
    phase = (design_module.get("phases") or [])[-1] if design_module.get("phases") else "Not Applicable"
    return {
        "nct_id": id_module.get("nctId") or "N/A",
        "title": title,
        "status": status_module.get("overallStatus") or "Unknown",
        "phase": phase,
        "sponsor": sponsor,
        "sponsor_lower": sponsor.lower(),
        "start_date": start_date,
        "enrollment": int(enrollment) if isinstance(enrollment, (int, float)) else 0,
        "conditions": " | ".join(conditions),
    }


def upsert_trial(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        """
        INSERT INTO trials (nct_id, title, status, phase, sponsor, sponsor_lower, start_date, enrollment, conditions, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(nct_id) DO UPDATE SET
            title=excluded.title,
            status=excluded.status,
            phase=excluded.phase,
            sponsor=excluded.sponsor,
            sponsor_lower=excluded.sponsor_lower,
            start_date=excluded.start_date,
            enrollment=excluded.enrollment,
            conditions=excluded.conditions,
            created_at=datetime('now')
        """,
        (
            row["nct_id"],
            row["title"],
            row["status"],
            row["phase"],
            row["sponsor"],
            row["sponsor_lower"],
            row["start_date"],
            row["enrollment"],
            row["conditions"],
        ),
    )


def sync_database(
    db_path: Path = DB_PATH,
    fetch_page_fn: Callable[..., dict] = fetch_page,
) -> dict[str, int | str]:
    token = None
    total_rows = 0
    with closing(sqlite3.connect(db_path)) as conn, conn:
        init_db(conn)
        page = 1
        while True:
            payload = fetch_page_fn(token=token)
            studies = payload.get("studies") or []
            if not studies:
                break

            for study in studies:
                upsert_trial(conn, normalize_study(study))
                total_rows += 1

            token = payload.get("nextPageToken")
            print(f"Fetched page {page}: {len(studies)} studies (total saved: {total_rows})")
            page += 1

            if not token:
                break

        conn.execute(
            """
            INSERT INTO sync_metadata (key, value)
            VALUES ('last_synced_at', datetime('now'))
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """
        )
        total_count = conn.execute("SELECT COUNT(*) FROM trials").fetchone()[0]
        last_synced_at = conn.execute(
            "SELECT value FROM sync_metadata WHERE key = 'last_synced_at'"
        ).fetchone()[0]

    return {
        "records_received": total_rows,
        "count": total_count,
        "last_synced_at": last_synced_at,
    }


def main() -> None:
    result = sync_database()
    print(f"Database created at: {DB_PATH}")
    print(f"Total records saved: {result['records_received']}")


if __name__ == "__main__":
    main()
