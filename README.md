# Intellitrials

## Clinical trials dashboard

Run the local server from the repository root:

```powershell
python trial_db_server.py
```

Open [http://127.0.0.1:8000/ctg.html](http://127.0.0.1:8000/ctg.html). The dashboard reads its saved trials from `data/clinical_trials.db`. Use **Refresh** to fetch the current industry-sponsored interventional trials from ClinicalTrials.gov and update the database. The first run with an empty database also performs an initial fetch.

The server provides `GET /api/trials` for saved trial records and `POST /api/trials/refresh` to update them. To perform a refresh without opening the dashboard, run:

```powershell
python data/build_trials_db.py
```

When hosted as a static GitHub Pages site, the dashboard fetches ClinicalTrials.gov directly instead of calling the local database server. Mobile browsers load at most 5,000 trials to reduce memory use; desktop browsers load at most 50,000.
