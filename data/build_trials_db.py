from __future__ import annotations

import json
import sqlite3
import urllib.parse
import urllib.request
from pathlib import Path

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
    title = id_module.get("officialTitle") or "No title"
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


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    token = None
    page = 1
    total_rows = 0

    while True:
        payload = fetch_page(token=token)
        studies = payload.get("studies") or []
        if not studies:
            break

        for study in studies:
            row = normalize_study(study)
            upsert_trial(conn, row)
            total_rows += 1

        token = payload.get("nextPageToken")
        print(f"Fetched page {page}: {len(studies)} studies (total saved: {total_rows})")
        page += 1

        if not token:
            break

    conn.commit()
    conn.close()
    print(f"Database created at: {DB_PATH}")
    print(f"Total records saved: {total_rows}")


if __name__ == "__main__":
    main()
