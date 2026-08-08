import json
import sqlite3
from pathlib import Path

root = Path(__file__).resolve().parent
src = root / 'clinical_trials.db'
out = root / 'clinical_trials.json'

conn = sqlite3.connect(src)
rows = conn.execute(
    "SELECT nct_id, title, status, phase, sponsor, start_date, enrollment, conditions FROM trials ORDER BY start_date DESC, nct_id DESC"
).fetchall()
conn.close()

payload = [
    {
        'nct_id': row[0],
        'title': row[1],
        'status': row[2],
        'phase': row[3],
        'sponsor': row[4],
        'start_date': row[5],
        'enrollment': row[6],
        'conditions': row[7],
    }
    for row in rows
]

with out.open('w', encoding='utf-8') as f:
    json.dump(payload, f, ensure_ascii=False)

print(f'Exported {len(payload)} trials to {out}')
