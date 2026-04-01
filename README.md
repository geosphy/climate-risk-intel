# 🌍 ClimateRisk Intel

**AI-Native Open Source Climate Risk Intelligence Platform**

Enter any address or zip code → get instant flood, heat, and storm risk intelligence for your physical asset — powered by World Bank climate data, CLIMADA, IBM Prithvi, and Claude AI.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![Next.js 14](https://img.shields.io/badge/Next.js-14-black.svg)](https://nextjs.org)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

---

## Demo

> Enter `"Houston, TX 77002"` → Receive flood, storm, and heat risk scores with an AI-generated narrative report.

---

## Features

- **Address Intelligence:** Type any address or zip code worldwide
- **Multi-Hazard Coverage:** Flood & Sea Level Rise, Extreme Heat, Storm & Wind
- **AI-Generated Reports:** Plain English risk narratives via Claude AI
- **Interactive Maps:** Leaflet.js maps with color-coded risk overlays
- **Open Data:** Built on World Bank, FEMA, NOAA, and CLIMADA datasets
- **API-First:** REST API for integration with existing platforms

---

## Data Sources

| Source | Data Provided | License |
|--------|--------------|---------|
| [World Bank CCKP](https://climateknowledgeportal.worldbank.org/) | Climate projections (temp, precipitation) | CC BY 4.0 |
| [FEMA OpenFEMA](https://www.fema.gov/about/openfema/api) | Flood zone classification | Public Domain |
| [NOAA CDO](https://www.ncei.noaa.gov/cdo-web/) | Historical storms and heat events | Public Domain |
| [CLIMADA](https://github.com/CLIMADA-project/climada_python) | Risk computation engine | LGPL-3.0 |
| [IBM Prithvi](https://huggingface.co/ibm-nasa-geospatial) | Geospatial AI (land cover) | Apache 2.0 |
| [OpenStreetMap](https://nominatim.org/) | Geocoding | ODbL |

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 20+
- NOAA API token (free): https://www.ncdc.noaa.gov/cdo-web/token
- Anthropic API key (for AI reports): https://console.anthropic.com

### 1. Clone the repo
```bash
git clone https://github.com/YOUR_USERNAME/climate-risk-intel.git
cd climate-risk-intel
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env and add your NOAA_TOKEN and ANTHROPIC_API_KEY
```

### 3. Run with Docker Compose
```bash
docker compose up --build
```

Open http://localhost:3000

### 4. Run manually (development)
```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

---

## API Reference

### POST `/api/risk`

Request:
```json
{
  "address": "Houston, TX 77002",
  "asset_type": "building"
}
```

Response:
```json
{
  "address": "Houston, TX 77002",
  "canonical_address": "Houston, Harris County, Texas, United States",
  "latitude": 29.7604,
  "longitude": -95.3698,
  "flood_risk": {
    "score": 0.87,
    "level": "Extreme",
    "confidence": "High",
    "details": { "fema_zone": "AE", "climada_return_period": 10 }
  },
  "heat_risk": {
    "score": 0.72,
    "level": "High",
    "confidence": "High",
    "details": { "avg_max_temp_c": 34.2, "extreme_heat_days_per_year": 42 }
  },
  "storm_risk": {
    "score": 0.78,
    "level": "High",
    "confidence": "Medium",
    "details": { "historical_storms_per_decade": 12 }
  },
  "overall_risk": { "score": 0.83, "level": "Extreme" },
  "ai_narrative": "...",
  "data_sources": ["World Bank CCKP", "FEMA", "NOAA", "CLIMADA"],
  "generated_at": "2026-04-01T10:00:00Z"
}
```

### GET `/api/health`
Returns service health status.

---

## Building with Claude Code

This project is designed to be built using [Claude Code](https://www.anthropic.com/claude-code).
The `CLAUDE.md` file contains complete instructions for Claude Code to build the entire system.

```bash
# Install Claude Code
npm install -g @anthropic/claude-code

# Start Claude Code in the project directory
claude
```

Then give Claude Code these prompts sequentially:
1. `Build the FastAPI backend following CLAUDE.md`
2. `Build the Next.js frontend following CLAUDE.md`
3. `Add Docker configuration`
4. `Run the tests`

---

## Roadmap

- [ ] v0.1 — Flood, Heat, Storm risk for US addresses
- [ ] v0.2 — Global address support, wildfire risk
- [ ] v0.3 — NVIDIA Earth-2 high-resolution simulations
- [ ] v0.3 — Time-series projections (2030 / 2050 / 2080)
- [ ] v0.4 — PDF report export, portfolio upload (CSV)
- [ ] v1.0 — Multi-tenant API, rate limiting, enterprise features

---

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md).

Areas most needed:
- Additional hazard modules (wildfire, drought)
- International data sources beyond FEMA
- Performance optimization for CLIMADA
- Frontend UX improvements

---

## License

MIT License — see [LICENSE](LICENSE)

---

## Acknowledgments

Built on the shoulders of giants: CLIMADA (ETH Zurich), IBM Prithvi (IBM Research + NASA), World Bank Climate Knowledge Portal, FEMA, and NOAA.
