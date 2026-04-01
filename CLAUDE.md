# ClimateRisk Intel — Claude Code Instructions

This file tells Claude Code how to build and maintain the ClimateRisk Intel platform.
Read this entire file before writing any code.

## Project Overview

ClimateRisk Intel is an AI-Native open-source platform for climate risk intelligence.
A user enters an address or pin code and receives a structured risk report covering:
- **Flood & Sea Level Rise Risk**
- **Extreme Heat Risk**
- **Storm & Wind Risk**

## Tech Stack

- **Backend:** Python 3.11, FastAPI, CLIMADA, httpx (async HTTP)
- **Frontend:** Next.js 14 (App Router), TypeScript, Tailwind CSS, Leaflet.js
- **AI:** Claude API (anthropic SDK) for narrative generation; IBM Prithvi via HuggingFace
- **Data Sources:**
  - World Bank CCKP REST API (no auth needed)
  - FEMA OpenFEMA API (no auth needed)
  - NOAA CDO API (token in env: NOAA_TOKEN)
  - CLIMADA Python library (pip package)
  - Nominatim OSM (no auth needed)
- **Config:** Environment variables via `.env` file, loaded with python-dotenv / Next.js built-in

## Architecture Rules

1. All backend logic lives in `backend/app/services/`. Each data source has its own service file.
2. Services are async (use `async def` and `httpx.AsyncClient`).
3. The FastAPI router in `backend/app/api/routes/risk.py` orchestrates service calls in parallel using `asyncio.gather()`.
4. Pydantic models in `backend/app/models/schemas.py` define all request/response shapes.
5. The frontend NEVER calls external APIs directly — everything goes through the FastAPI backend.
6. Frontend components are in `frontend/src/components/`. Each component is a single-responsibility React functional component with TypeScript.
7. Use Tailwind CSS for all styling. No separate CSS files.
8. Leaflet map component must be dynamically imported (SSR disabled) in Next.js.

## Data Models

### Request
```python
class RiskRequest(BaseModel):
    address: str          # "123 Main St, Houston TX" or "77002"
    asset_type: str = "building"   # building | land | infrastructure
```

### Response
```python
class HazardScore(BaseModel):
    score: float          # 0.0 to 1.0
    level: str            # "Low" | "Medium" | "High" | "Extreme"
    confidence: str       # "Low" | "Medium" | "High"
    details: dict         # Source-specific metadata

class RiskReport(BaseModel):
    address: str
    canonical_address: str
    latitude: float
    longitude: float
    flood_risk: HazardScore
    heat_risk: HazardScore
    storm_risk: HazardScore
    overall_risk: HazardScore
    ai_narrative: str     # AI-generated plain English summary
    data_sources: list[str]
    generated_at: str     # ISO timestamp
```

## Service Implementation Details

### geocoding.py
- Use Nominatim: `https://nominatim.openstreetmap.org/search`
- Query params: `q={address}&format=json&limit=1`
- Add User-Agent header: `ClimateRiskIntel/1.0`
- Return: lat, lon, canonical display name

### world_bank.py
- Base URL: `https://cckpapi.worldbank.org/cckp/v1/`
- Fetch temperature anomaly and precipitation for the country/region containing the lat/lon
- Use endpoint pattern: `/cckp/v1/cmip6/{variable}/{scenario}/{period}/{country}`
- Map lat/lon to ISO country code using `pycountry-convert` or a simple lookup
- Return: projected temperature increase (°C) and precipitation change (%) for 2050 under SSP2-4.5

### fema.py
- Use OpenFEMA National Flood Hazard Layer API
- Endpoint: `https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query`
- Query: spatial intersection with a small bounding box around lat/lon
- Return: flood zone code (A, AE, X, etc.) and description

### noaa.py
- Token: env var NOAA_TOKEN
- Use NCEI API: `https://www.ncei.noaa.gov/cdo-web/api/v2/`
- Fetch nearest station data for: TMAX (temperature), PRCP (precipitation), storm events
- Also use Storm Events CSV data for historical storm frequency at the state level
- Return: avg max temperature, historical storm count, extreme heat days per year

### climada_engine.py
- Import: `from climada.hazard import Flood, TropCyclone`
- For flood: use CLIMADA's river flood hazard for the lat/lon point
- For storm: use IBTrACS tropical cyclone track data to compute wind speed probability
- Compute impact using CLIMADA's impact functions
- Return: exceedance probability and return period for each hazard

### prithvi.py
- Model: `ibm-nasa-geospatial/Prithvi-EO-2.0` on HuggingFace
- Use the transformers pipeline for geospatial inference
- This is optional/enhancement — gracefully skip if model unavailable
- Use for: land cover classification at the asset location

### report_generator.py
- Use Anthropic Python SDK: `import anthropic`
- API key from env: ANTHROPIC_API_KEY
- Compose a structured prompt from all risk scores and metadata
- Ask Claude to generate a 3-paragraph plain English risk narrative:
  1. Overall risk summary
  2. Key hazard details
  3. Recommended actions for asset owners
- Model: claude-3-5-haiku-20241022 (fast and cost-effective for this use case)

## Scoring Algorithm

Convert raw data to normalized 0.0-1.0 scores:

### Flood Score
```
FEMA Zone A/AE/V = 0.85-1.0 (Extreme)
FEMA Zone AH/AO  = 0.65-0.84 (High)
FEMA Zone AR/A99 = 0.45-0.64 (Medium)
FEMA Zone X      = 0.10-0.44 (Low)
CLIMADA flood probability adjustment: ±0.15
```

### Heat Score
```
Avg Max Temp > 38°C = 0.85-1.0 (Extreme)
Avg Max Temp 33-38°C = 0.65-0.84 (High)
Avg Max Temp 28-33°C = 0.45-0.64 (Medium)
Avg Max Temp < 28°C = 0.10-0.44 (Low)
World Bank 2050 projection adjustment: +0.1 per +1°C projected increase
```

### Storm Score
```
Hurricane-prone coast (Category 3+ historical) = 0.85-1.0
Historical storm events > 10/decade = 0.65-0.84
Historical storm events 5-10/decade = 0.45-0.64
Historical storm events < 5/decade = 0.10-0.44
CLIMADA cyclone probability adjustment: ±0.15
```

### Overall Score
```
overall = max(flood, heat, storm) * 0.5 + mean(flood, heat, storm) * 0.5
```

## Frontend Component Behavior

### SearchBar.tsx
- Controlled input with debounce (300ms)
- On submit: POST to `/api/risk` with address
- Show loading spinner during API call
- On error: show error message with retry button

### RiskMap.tsx
- Leaflet map centered on returned lat/lon
- Marker at the address location
- Color-coded circle overlay based on overall risk score:
  - Green: Low (< 0.45)
  - Yellow: Medium (0.45-0.64)
  - Orange: High (0.65-0.84)
  - Red: Extreme (> 0.84)
- Map tiles: OpenStreetMap (free, no key)

### HazardCard.tsx
- Props: `{ type: 'flood' | 'heat' | 'storm', score: HazardScore }`
- Show icon, level badge, score bar, key detail
- Icons: use lucide-react (Waves for flood, Thermometer for heat, Wind for storm)

### RiskDashboard.tsx
- Grid of 3 HazardCard components
- Overall risk score prominently displayed
- Data sources attribution list

### RiskReport.tsx
- Display ai_narrative in a styled card
- "Generated by Claude AI" attribution
- Option to copy or share report text

## Environment Variables (.env)

```
# Backend
NOAA_TOKEN=your_noaa_token_here
ANTHROPIC_API_KEY=your_anthropic_key_here
BACKEND_PORT=8000
CORS_ORIGINS=http://localhost:3000

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Error Handling

- Each service must have try/except and return a default/null value on failure
- The risk endpoint must still return a partial report if 1-2 services fail
- Log all service failures with: `logger.warning(f"Service {name} failed: {e}")`
- Return HTTP 200 with partial data rather than HTTP 500 when possible
- Include `data_sources` list in response to show which sources were used

## Testing

- Backend: pytest + httpx AsyncClient for integration tests
- Test file: `backend/tests/test_risk_endpoint.py`
- Use a fixture with Houston TX (77002) as the test address
- Mock external API calls using `respx` library
- Frontend: no tests required for MVP

## Docker Setup

### backend/Dockerfile
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### frontend/Dockerfile
```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package*.json .
RUN npm ci
COPY . .
RUN npm run build
CMD ["npm", "start"]
```

### docker-compose.yml
Services: `backend` (port 8000) and `frontend` (port 3000).
Frontend depends_on backend.
Both services share an `.env` file at the root.

## Git Workflow

- Main branch: `main`
- Feature branches: `feature/service-name` (e.g. `feature/fema-service`)
- Commit message format: `feat: add FEMA flood zone service`
- Do NOT commit `.env` files — they're in `.gitignore`

## Code Style

- Python: follow PEP 8, use type hints everywhere, docstrings on all functions
- TypeScript: strict mode, no `any` types, functional components only
- All files must have a module-level docstring/comment explaining their purpose

## When Asked to "Build the Backend"

Execute in this order:
1. Create `backend/requirements.txt` with all dependencies
2. Create `backend/app/core/config.py` (settings from env vars)
3. Create `backend/app/models/schemas.py` (all Pydantic models)
4. Create each service file in `backend/app/services/`
5. Create `backend/app/api/routes/risk.py` (orchestration)
6. Create `backend/app/api/routes/health.py`
7. Create `backend/app/main.py` (FastAPI app, CORS, router registration)
8. Create `backend/tests/test_risk_endpoint.py`

## When Asked to "Build the Frontend"

Execute in this order:
1. Scaffold Next.js: `npx create-next-app@latest frontend --typescript --tailwind --app`
2. Install extra deps: `npm install leaflet @types/leaflet lucide-react`
3. Create `frontend/src/types/risk.ts`
4. Create `frontend/src/lib/api.ts`
5. Create each component in `frontend/src/components/`
6. Create `frontend/src/app/page.tsx` composing all components
7. Update `frontend/src/app/layout.tsx` with metadata

## Important Notes

- CLIMADA installation can be slow (~5 min first time). Alert the user and proceed.
- Nominatim has a 1 req/sec rate limit. Add a 1-second delay between geocoding requests.
- World Bank CCKP API uses country-level data. For local precision, weight by FEMA + NOAA data.
- IBM Prithvi model download is ~1.5GB. Make it optional and gracefully degrade.
- Always include data attribution in the UI for World Bank, FEMA, NOAA, OSM.
