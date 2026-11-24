# spotify-pipeline

Personal data pipeline that combines my full Spotify listening history (Extended Streaming History export) with incremental collection from the Web API, models the data as a fact table plus dimensions in SQLite, and ends in a Power BI dashboard. It exercises OAuth with refresh tokens, incremental ingestion with deduplication, dimensional modeling, and working around structural rate limits (the API no longer has batch endpoints).

## Setup

1. **Request the Extended Streaming History.** Account → Privacy → download your data, extended option (not the basic one, which only covers the last year). It arrives by email within a few days.
2. **Create an app in the Spotify Developer Dashboard.** Redirect URI: `http://127.0.0.1:8888/callback` (`localhost` is not accepted). The app name cannot start with "Spot".
3. Copy `.env.example` to `.env` and fill in the Client ID and Client Secret.
4. `python -m venv .venv` and `.venv\Scripts\pip install -r requirements.txt`.
5. **Get the refresh token:** `.venv\Scripts\python src\get_refresh_token.py`. It opens the browser, receives the callback on `127.0.0.1:8888`, saves the token and its issue date to `.env`, and validates it with `GET /me`.
6. `python src/db.py` to create the database and tables (`ingest_recent.py` also applies the schema).

## Usage

```powershell
.venv\Scripts\python src\ingest_recent.py   # last 50 plays -> fact_plays + dimensions
```

The API only keeps the last 50 plays, so the script must run often enough that no more than 50 tracks are played between runs. It logs a warning when it detects a gap.

### Scheduling (Windows)

A Task Scheduler task, `spotify-pipeline ingest_recent`, runs the script every hour and at logon using `pythonw.exe` (no console window). If the PC was off at the scheduled time, it runs as soon as possible. Logs go to `logs/ingest_recent.log`, rotated at 1 MB.

```powershell
$repo = "C:\path\to\spotify-pipeline"
$action = New-ScheduledTaskAction -Execute "$repo\.venv\Scripts\pythonw.exe" -Argument "src\ingest_recent.py" -WorkingDirectory $repo
$hourly = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1)
$logon = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "spotify-pipeline ingest_recent" -Action $action -Trigger $hourly,$logon -Settings $settings
```

Limitation: while the PC is off, plays from other devices are only captured if they are still among the last 50 when the task runs.

> **The refresh token expires 180 days after the original authorization** (refreshing does not extend it). Once expired, `/api/token` returns `400 invalid_grant`: run `get_refresh_token.py` again.

### Observed API limitations (Nov 2026)

- `GET /artists/{id}` no longer returns `genres` (null in testing; the docs mark the field as deprecated). Genre analysis needs another source.
- The token refresh did not return a new `refresh_token`; the original one stays valid.
- The `track` object in `recently-played` already contains every column of `dim_track` and `dim_album`, so per-ID enrichment is almost unnecessary for plays coming from the API.

## Design decisions

**Authentication**

- **Where to store the Client ID, secret, and refresh token without committing them**
  - Choice: a `.env` file at the repo root, listed in `.gitignore` before the first commit; `.env.example` with empty values is committed.
  - Why: a local, single-user project; a secrets vault would add complexity with no benefit. A secret committed once stays in the history, so `.gitignore` came first.
- **When to renew the access token** (always at startup, only on 401, or another rule)
  - Choice: on the first call of each run and whenever it is less than 5 minutes from expiring; if a 401 still comes back, force a refresh and retry once.
  - Why: each collection run takes seconds, so refreshing at startup is cheap and avoids a predictable 401. The margin covers long enrichment runs; the 401 retry covers a revoked token or a skewed clock.
- **Where to save a renewed refresh token** (a refresh may return a new token or none)
  - Choice: in `.env` itself, only when the response contains a `refresh_token` different from the current one. The issue date is kept in `SPOTIFY_REFRESH_TOKEN_ISSUED_AT`, and the script warns when fewer than 15 of the 180 days remain.
  - Why: the docs say the token may be missing from the response, in which case the current one remains valid; overwriting it with an empty value would break access. The token does not carry its own age, so the date has to be stored.

**Modeling and data**

- **Which source wins when the same play comes from both the export and the API**
  - Choice: a time cutoff. The export is the source of truth up to its `max(ts)`; API rows are only loaded with a `played_at` after that cutoff. `played_at` is stored in the canonical format `YYYY-MM-DDTHH:MM:SSZ` (UTC, second precision) for both sources.
  - Why: the export has second precision and the API has millisecond precision, and the export's `ts` has ±1 s or more of noise. Matching play by play would need a tolerance window and would still fail at the edges. The cutoff is simple, deterministic, and easy to explain, and it favors the export because it has `ms_played`, `skipped`, and `reason_*`.
- **Plays that are not music tracks (podcasts, audiobooks, video, orphan records)**
  - Choice: kept out of `fact_plays`; `ingest_history.py` only loads rows with a `spotify_track_uri` and logs how many it dropped, by type.
  - Why: the project analyzes music; these rows break the `NOT NULL` constraint on `track_name`/`artist_name` and have no matching dimension. Logging the count keeps the loss visible.
- **Most-played genre: SQL view or Power BI measure over the bridge table**
  - Choice: _to be decided_
  - Why: _to be decided_
- **Dimension refresh policy** (never, every 90 days, or artists only)
  - Choice: _to be decided_
  - Why: _to be decided_
- **What counts as a "play"**
  - Choice: in the export, `ms_played >= 30000`. API rows count as plays (they have no `ms_played`). Rows under 30 s stay in the fact table; the filter is applied at analysis time, not at load time.
  - Why: 30 s is Spotify for Artists' official stream-counting rule, so it is defensible. Keeping short rows preserves skip analysis. Documented limitation: the API does not allow applying the same criterion, and reportedly it already omits most skips, but not all.

## Project structure

```
spotify-pipeline/
├── .gitignore
├── .env.example
├── README.md
├── requirements.txt
├── docs/                    # study notes on the API and the export (Portuguese)
├── sql/
│   └── schema.sql           # fact, dimensions, bridge, and enrichment queue
├── src/
│   ├── get_refresh_token.py # OAuth handshake (once every 180 days)
│   ├── auth.py              # refresh token -> access token
│   ├── spotify_api.py       # GET with retries, 401 handling, and rate limiting (429)
│   ├── ingest_recent.py     # /me/player/recently-played -> fact_plays + dim_*
│   ├── ingest_history.py    # export JSON -> fact_plays
│   ├── enrich.py            # IDs without metadata -> dim_*
│   └── db.py                # connection + schema init
└── data/
    ├── raw/                 # Spotify export (git-ignored)
    └── spotify.db           # SQLite database (git-ignored)
```
