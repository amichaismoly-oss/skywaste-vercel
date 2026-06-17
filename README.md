# SkyWaste AI ✈️♻️ — Web App (Vercel)

Mobile-friendly dashboard for **International Catering Waste (ICW) buffer optimization**.
The polished AeroWaste dashboard front-end is wired to the **real SkyWaste optimization
engine**, which runs as a Python serverless function on Vercel.

- **Frontend** — static dashboard in [`public/`](public/) (responsive; usable from a phone).
- **Backend** — FastAPI engine in [`api/index.py`](api/index.py), exposed at `/api/*`.
- **Engine** — the real `skywaste.optimization` package in [`skywaste/`](skywaste/),
  running in stateless mode (bundled static data, no Supabase needed).

The dashboard's **Live ICW Optimization Engine** card calls `POST /api/optimize/flight`
and shows the real recommended buffer, savings breakdown (disposal + fuel + CORSIA),
CO₂ saved, ICW category, ABP regime, and regulatory risk.

---

## API

| Method | Path | Description |
|--------|------|-------------|
| GET  | `/api/health` | Liveness + mode (`stateless` / `supabase`) |
| GET  | `/api/airports` | Reference airports + disposal costs |
| POST | `/api/optimize/flight` | Single-flight buffer recommendation |
| POST | `/api/optimize/route` | Aggregate + annualised savings |
| GET  | `/api/docs` | Swagger UI |

Example:
```bash
curl -X POST https://<your-app>.vercel.app/api/optimize/flight \
  -H "Content-Type: application/json" \
  -d '{"flight_number":"LY001","origin_airport":"TLV","destination_airport":"JFK",
       "departure_date":"2026-06-17","aircraft_type":"B789",
       "passenger_count":280,"route_distance_km":9100}'
```

---

## Run locally

```bash
pip install -r requirements.txt uvicorn
python dev_server.py          # → http://127.0.0.1:8000
```

`dev_server.py` mounts `public/` on top of the API so the frontend's same-origin
`/api/...` calls work exactly like they do on Vercel. **It is local-only — Vercel
ignores it** (only `/api/*` becomes functions and `/public` is the static root).

---

## Deploy to Vercel (via GitHub)

1. **Create a GitHub repo** and push this folder (see commands below).
2. Go to **vercel.com → Add New → Project → Import** your GitHub repo.
3. Framework preset: **Other** (zero config — `vercel.json` handles the rest).
4. Click **Deploy**. Every `git push` redeploys automatically.

Push commands:
```bash
git init && git add -A && git commit -m "SkyWaste AI web app"
git branch -M main
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

### Optional environment variables (Vercel → Settings → Environment Variables)
The app runs fully in stateless/demo mode with **no** env vars. To enable the live
data sources from the full project:

| Var | Effect |
|-----|--------|
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | Use the live Supabase DB instead of bundled static data |
| `SKYWASTE_ENABLE_WAHIS=1` | Poll the live WOAH/WAHIS outbreak feed at request time |

---

## Notes on the serverless build

This deploy target is a slimmed copy of the full `skywaste-ai` engine, adapted for
Vercel functions:

- **Airports** — `skywaste/optimization/data/airports.py` ships a curated static
  IATA→country map instead of downloading the 90k-row OurAirports CSV (read-only FS).
- **Outbreaks** — `skywaste/optimization/data/wahis_live.py` is disabled by default
  (`SKYWASTE_ENABLE_WAHIS=1` to turn on) to keep cold starts within the time budget.
- **DB** — `skywaste/db.py` is a no-supabase stub; the engine falls back to its
  bundled disposal-cost table and ABP regimes, producing identical math.

The buffer/savings calculations (`engine.py`, `models.py`) are **unchanged** from the
full project, so results match the original API exactly.

---

## BTS real flight data (T-100)

The dashboard's **Real BTS route** selector pulls genuine route statistics from the
BTS **T-100 Segment** dataset (avg passengers/flight, distance, dominant aircraft) and
feeds them into the optimization engine.

BTS publishes **no live API** for granular T-100 data — it's a one-time CSV download
from TranStats. The ingest is therefore offline + bundled:

1. **Download the CSV** from TranStats T-100 Segment (free, no account):
   <https://www.transtats.bts.gov/DL_SelectFields.aspx?gnoyr_VQ=GED> →
   table **T-100 Segment (All Carriers)** → pick a year/month → select columns
   `PASSENGERS, DEPARTURES_PERFORMED, DISTANCE, ORIGIN, DEST, AIRCRAFT_TYPE,
   UNIQUE_CARRIER, YEAR, MONTH` → **Download** → unzip.
2. **Ingest** it into the bundled JSON the API serves:
   ```bash
   python scripts/ingest_bts_t100.py path/to/T_T100_SEGMENT.csv --top 40
   ```
   This writes `skywaste/optimization/data/bts_routes.json` (served at
   `GET /api/bts/routes`).
3. **Redeploy** (`npx vercel --prod`, or just `git push` once auto-deploy is on).

Until a CSV is ingested the selector shows "No BTS data ingested" — the app never
ships fabricated route data.

---

## Auto-deploy (GitHub → Vercel)

To make every `git push` redeploy automatically:

```bash
gh auth login                                   # one-time GitHub auth
gh repo create skywaste-ai --public --source=. --push
npx vercel git connect                          # link the Vercel project to the repo
```

After this, pushing to `main` triggers a production deploy with no manual step.
