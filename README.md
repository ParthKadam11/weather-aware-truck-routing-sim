# Weather-Aware Truck Routing

Take-home assessment: help a truck driver pick the **safest** of three routes using weather at each checkpoint (timed to ETA), load weight, and travel time.

**Stack:** Django + DRF (thin API) · plain Python core (fully unit-tested) · React + Vite + MUI · MapLibre GL + deck.gl

---

## Quick start (local)

### Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # optional
python manage.py migrate --run-syncdb
python manage.py runserver 8000
```

Core unit tests (no network):

```bash
cd backend && python -m pytest
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — Vite proxies `/api` → `http://127.0.0.1:8000`.

### Demo storm

Toggle **Demo storm** in the UI, or set `DEMO_STORM=1` on the backend. A synthetic severe cell is overlaid on the corridor so recommendation ranking visibly changes.

---

## Architecture

```
┌─────────────┐   POST /api/routes/analyze    ┌──────────────────┐
│  React UI   │ ─────────────────────────────►│  Django / DRF    │
│ MapLibre +  │   POST /api/weather/heatmap   │  (views / ser.)  │
│ deck.gl     │ ◄─────────────────────────────│                  │
└─────────────┘   48h frames (one fetch)      └────────┬─────────┘
                                                       │
                       ┌───────────────────────────────┼────────────────┐
                       ▼                               ▼                ▼
                 ┌──────────┐                   ┌──────────┐     ┌────────────┐
                 │  core/*  │◄── weather@ETA ───│ Open-Meteo│     │ OSRM /     │
                 │ risk,ETA │                   │ (+ cache) │     │ Photon     │
                 │ recommend│                   └──────────┘     └────────────┘
                 └──────────┘
```

**Django layer is intentionally thin.** Business rules live in `backend/core/` with **zero Django imports**, so they are easy to unit-test and reuse.

| Django piece | Role (short) |
|---|---|
| **settings** | Config: CORS, env flags (`DEMO_STORM`), provider URLs |
| **serializers** | Validate JSON in (origin, load, interval ∈ {10,25,50}, …) |
| **views** | HTTP glue: validate → `services.py` → JSON |
| **urls** | `/api/health`, `/api/routes/analyze`, `/api/weather/heatmap` |
| **models** | None — no persistence for this assessment |

---

## Risk model

Per checkpoint, classify wind / rain / snow independently, take the **worst**, then apply **load rules**.

| | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| **Wind (mph)** | &lt;25 | 25–34 | 35–44 | 45–54 | ≥55 |
| **Rain (in/hr)** | &lt;0.10 | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | &gt;1.00 |
| **Snow (in/hr)** | &lt;0.5 | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | &gt;3.0 |

Shared numeric edges (e.g. rain 0.25) resolve to the **higher** band (conservative).

**Load rules**

- ≥55 mph → **No Travel** (any load)
- 45–54 mph + **&gt;30,000 lb** → **No Travel**
- 35–44 mph + **&gt;40,000 lb** → **Severe**

**Miles per risk level:** each segment’s miles are attributed to the risk of the checkpoint at its end.

**Average risk score:** Low=1 … No Travel=5, mean over checkpoints.

**Recommendation order**

1. Fewest **Severe + No Travel** miles  
2. Fewest **High** miles  
3. Lowest average risk  
4. Shortest duration  

A plain-English `reason` explains the pick vs the runner-up.

---

## APIs used (free, no keys)

| Provider | Use | Limits / notes |
|---|---|---|
| [OSRM](https://router.project-osrm.org) public demo | Driving routes + alternatives | Fair-use; no SLA. Via-point offsets if &lt;3 unique routes. |
| [Photon](https://photon.komoot.io) | Geocoding | Public; be polite with volume. |
| [Open-Meteo](https://api.open-meteo.com) | Hourly wind (mph), precip (inch), snowfall (cm→in) | Free non-commercial; we batch/dedupe coords + TTL cache. |
| [OpenFreeMap](https://openfreemap.org) Liberty | Map basemap (MapLibre) | Free, no API key. (Carto public tiles now require a key.) |

Weather cache: in-memory TTL (default 15 min). Redis-ready interface in `core/cache.py`.

---

## Deploy

**Backend (Render):** `render.yaml` + `backend/Dockerfile` (Python 3.12, gunicorn). Set `CORS_ALLOWED_ORIGINS` to your Vercel URL.

**Frontend (Vercel):** root `frontend/`. Set `VITE_API_BASE_URL=https://<your-render-service>.onrender.com/api`.

---

## Assumptions & tradeoffs

1. **ETA model** — OSRM gives total duration; we distribute time by distance fraction. Per-leg traffic would need a paid router.
2. **Exactly 3 routes** — OSRM alternatives + perpendicular via-points; if the network still collapses, we pad labeled variants so the UI always has three cards.
3. **Checkpoint weather hour** — floor to the forecast hour of the UTC ETA.
4. **Heatmap** — one corridor grid fetch (capped ~80 cells); slider only swaps `frames[h]` client-side (no refetch).
5. **No auth / no DB** — correct for a routing demo; production would store trips and rate-limit by user.
6. **Public OSRM** — fine for review; production should self-host or use a commercial truck-aware router (height/weight restrictions).

---

## What I'd do with more time

- Truck profile constraints (HAZMAT, height, weight) via a truck-aware router  
- Redis cache + request coalescing under concurrent reviewers  
- Per-segment OSRM annotations for better ETAs  
- Playwright e2e: form → map → demo storm flips recommendation  
- Progressive heatmap (WebGL tile) for continental corridors  
- Export PDF trip brief for the driver  

---

## Loom walkthrough (outline)

1. Form inputs + interval + demo storm off → 3 routes, recommended card, map  
2. Checkpoint hover: ETA local + wind/rain/snow + risk color  
3. Heatmap slider 0–48h (Network tab: no extra calls while sliding)  
4. Demo storm on → re-analyze → recommendation reason changes  
5. Point at `core/risk.py` tests (98 pytest cases on every threshold)

---

## Project layout

```
backend/core/          # pure Python logic + risk tables
backend/api/           # thin DRF + providers
backend/tests/         # pytest
frontend/src/          # React UI + MapLibre/deck.gl
render.yaml            # Render blueprint
```
