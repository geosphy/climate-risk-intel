# 🌍 ClimateRisk Intel — Open Source Setup Guide
### From Zero to a Working Climate Risk Intelligence Platform

---

## What You're Building

**ClimateRisk Intel** is an AI-Native, open-source platform that lets anyone type in an address or pin code and instantly receive a climate risk intelligence report for that physical asset — covering **Flood Risk**, **Extreme Heat**, and **Storm & Wind** hazards.

**Stack at a glance:**
- **Frontend:** Next.js + React (interactive map + risk dashboard)
- **Backend:** Python FastAPI (data ingestion, risk computation, AI inference)
- **AI/ML:** IBM Prithvi (Hugging Face, free), CLIMADA risk engine
- **Data Sources:** World Bank CCKP API, CLIMADA, FEMA flood zones, NOAA storm history
- **Geocoding:** OpenStreetMap Nominatim (free, no key needed)
- **Infra:** Runs locally or Docker; deployable to any cloud

---

## System Architecture

```
User Input (Address / Pin Code)
         │
         ▼
┌─────────────────────────────────────────────────────┐
│                   Next.js Frontend                   │
│  • Address search box                                │
│  • Interactive map (Leaflet.js)                      │
│  • Risk score dashboard (Flood / Heat / Storm)       │
│  • AI-generated narrative report                     │
└──────────────────────┬──────────────────────────────┘
                       │ REST API calls
                       ▼
┌─────────────────────────────────────────────────────┐
│                 FastAPI Backend                       │
│                                                      │
│  1. Geocoding Service                                │
│     └─ Nominatim (address → lat/lon)                 │
│                                                      │
│  2. Climate Data Aggregator                          │
│     ├─ World Bank CCKP API (temp/precip projections) │
│     ├─ FEMA API (flood zone classification)          │
│     └─ NOAA CDO API (historical storms & heat)       │
│                                                      │
│  3. Risk Engine                                      │
│     └─ CLIMADA Python (hazard + impact computation)  │
│                                                      │
│  4. AI Enhancement Layer                             │
│     ├─ IBM Prithvi / HuggingFace (downscaling)       │
│     └─ LLM (Claude API - narrative report generator) │
│                                                      │
│  5. Risk Report Composer                             │
│     └─ Aggregates scores → structured JSON           │
└─────────────────────────────────────────────────────┘
```

---

## Project Folder Structure

```
climate-risk-intel/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app entry point
│   │   ├── api/
│   │   │   └── routes/
│   │   │       ├── risk.py         # /api/risk endpoint
│   │   │       └── health.py       # /api/health endpoint
│   │   ├── services/
│   │   │   ├── geocoding.py        # Address → lat/lon
│   │   │   ├── world_bank.py       # World Bank CCKP API client
│   │   │   ├── fema.py             # FEMA flood zone API client
│   │   │   ├── noaa.py             # NOAA CDO API client
│   │   │   ├── climada_engine.py   # CLIMADA risk computation
│   │   │   ├── prithvi.py          # IBM Prithvi HuggingFace client
│   │   │   └── report_generator.py # AI narrative generation
│   │   ├── models/
│   │   │   └── schemas.py          # Pydantic data models
│   │   └── core/
│   │       └── config.py           # Environment config
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/                    # Next.js App Router
│   │   │   ├── page.tsx            # Home page
│   │   │   └── layout.tsx
│   │   ├── components/
│   │   │   ├── SearchBar.tsx       # Address input
│   │   │   ├── RiskMap.tsx         # Leaflet map component
│   │   │   ├── RiskDashboard.tsx   # Score cards
│   │   │   ├── RiskReport.tsx      # AI narrative display
│   │   │   └── HazardCard.tsx      # Individual hazard card
│   │   ├── lib/
│   │   │   └── api.ts              # API client functions
│   │   └── types/
│   │       └── risk.ts             # TypeScript types
│   ├── package.json
│   └── Dockerfile
├── data/
│   └── sample/                     # Sample datasets for testing
├── docs/
│   ├── architecture.md
│   └── data-sources.md
├── CLAUDE.md                       # ← Claude Code instructions (see below)
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

---

## Step 1: Create Your GitHub Repository

1. Go to **github.com** and click the **"+"** icon → **New repository**
2. Name it: `climate-risk-intel`
3. Set to **Public** (open source)
4. Check **"Add a README file"**
5. Choose **MIT License**
6. Click **Create repository**

Then on your computer, open your terminal:

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/climate-risk-intel.git
cd climate-risk-intel
```

---

## Step 2: Install Prerequisites

### Python (3.11+)
```bash
# Check if installed
python3 --version

# If not, install from https://python.org
```

### Node.js (20+)
```bash
# Check if installed
node --version

# If not, install from https://nodejs.org
```

### Claude Code CLI
```bash
# Install globally via npm
npm install -g @anthropic/claude-code

# Verify installation
claude --version
```

---

## Step 3: Get Your API Keys

You'll need these free API tokens. Add them to a `.env` file later:

| Service | Where to get it | Required? |
|---------|----------------|-----------|
| **NOAA CDO** | https://www.ncdc.noaa.gov/cdo-web/token | Yes |
| **Anthropic (Claude)** | https://console.anthropic.com | Yes (for AI reports) |
| **World Bank CCKP** | No key needed | — |
| **FEMA** | No key needed | — |
| **Nominatim** | No key needed | — |
| **IBM Prithvi** | No key needed (HuggingFace) | — |

---

## Step 4: Set Up the Project with Claude Code

This is where the magic happens. Claude Code will **write most of the code for you** by following the `CLAUDE.md` file you place in the repo.

### 4a. Copy the project files into your repo
Place the files from this package into your cloned `climate-risk-intel/` folder.

### 4b. Create your `.env` file
```bash
cp .env.example .env
# Then edit .env and fill in your NOAA_TOKEN and ANTHROPIC_API_KEY
```

### 4c. Start Claude Code
```bash
# From inside your project folder
cd climate-risk-intel
claude
```

Claude Code will read `CLAUDE.md` and understand the entire project context.

### 4d. Build the backend
Type these prompts into Claude Code one at a time:

```
> Build the FastAPI backend following the structure in CLAUDE.md.
  Start with the geocoding service and the /api/risk endpoint.
```

```
> Implement the World Bank CCKP service to fetch temperature and
  precipitation projections for a given lat/lon coordinate.
```

```
> Implement the FEMA flood zone lookup service using their OpenFEMA API.
```

```
> Implement the NOAA historical storm and heat data service.
```

```
> Implement the CLIMADA risk engine to compute a flood risk score
  and storm risk score for a given lat/lon.
```

```
> Implement the report_generator.py that calls the Claude API to
  generate a human-readable risk narrative from the aggregated data.
```

### 4e. Build the frontend
```
> Create the Next.js frontend with a search bar, an interactive
  Leaflet map, and risk score cards for Flood, Heat, and Storm risk.
```

```
> Wire up the frontend to call the FastAPI backend /api/risk endpoint
  and display the results on the map and dashboard.
```

### 4f. Run the full stack
```bash
# Terminal 1: Start backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# Terminal 2: Start frontend
cd frontend
npm install
npm run dev

# Open http://localhost:3000
```

---

## Step 5: Test Your First Risk Query

With both servers running, open your browser to `http://localhost:3000`.

Try entering:
- `"Houston, TX 77002"` — high flood + storm risk city
- `"Phoenix, AZ 85001"` — extreme heat risk city
- `"Miami, FL 33101"` — sea level rise + storm risk

You should see a map pin, colored risk score cards (Low/Medium/High/Extreme), and an AI-generated risk narrative.

---

## Step 6: Push to GitHub

```bash
git add .
git commit -m "feat: initial climate risk intel platform"
git push origin main
```

---

## Step 7: Make it Open Source — Best Practices

1. **Tag your release:** `git tag v0.1.0-alpha && git push --tags`
2. **Add GitHub topics** in the repo settings: `climate-risk`, `ai`, `open-source`, `fastapi`, `nextjs`, `climada`
3. **Enable GitHub Issues** for community bug reports
4. **Add a CONTRIBUTING.md** (Claude Code can generate this for you)
5. **Add GitHub Actions CI** (Claude Code can set this up too)

---

## Roadmap — What to Build Next

| Phase | Feature |
|-------|---------|
| v0.2 | Wildfire risk module |
| v0.2 | CSV bulk upload (multiple assets) |
| v0.3 | NVIDIA Earth-2 API integration for high-res simulation |
| v0.3 | Time-series projections (2030, 2050, 2080 scenarios) |
| v0.4 | PDF risk report export |
| v0.4 | Portfolio-level risk aggregation |
| v1.0 | Multi-tenant API with rate limiting |

---

## Getting Help

- **Claude Code:** Type your question directly in the Claude Code terminal
- **CLIMADA docs:** https://climada-python.readthedocs.io/
- **World Bank API:** https://climateknowledgeportal.worldbank.org/
- **Project GitHub Issues:** Use for tracking bugs and features

---

*Built with ❤️ by the open-source climate community.*
