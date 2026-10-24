# S2 – Emission Engine and DevOps (explained simply)

Owner: Tuba Jabeen (Member 2). Works together with S1 (data and login), S3 (analytics) and S4 (AI coach).

## 1. What does S2 do?
S2 turns **activities** (for example "12,000 kWh of electricity") into **CO2 emissions** (kg CO2e) and **cost** (EUR).

    emissions (kg CO2e) = amount x emission factor
    cost (EUR)          = amount x tariff

Example: 12,000 kWh x 0.363 kg/kWh = **4,356 kg CO2e**. This is our reference test.

S2 also runs the project: Docker (one command starts everything) and GitHub Actions (tests run automatically).

## 2. Words you need
| Word | Meaning |
|---|---|
| Activity | One thing a company did, e.g. used 200 m3 gas. Saved by S1. |
| Emission factor | How many kg CO2e one unit causes (kg per kWh, per litre, ...). Comes from an official source. |
| Tariff | What one unit costs in EUR. |
| Scope 1 / 2 / 3 | 1 = own fuel burning, 2 = bought electricity, 3 = everything else (travel, waste, water). |
| Region | Country code (DE) or GLOBAL (fallback for everyone). |
| Version | When a factor changes, a new version is created. The old one is kept. |
| Trace | A short record showing exactly how a result was calculated. |

## 3. How a calculation works (step by step)
1. S1 saves an activity and calls S2 (`safe_calculate_activity`).
2. S2 **converts the unit** if needed (MWh -> kWh, tonne -> kg, m3 -> litre). Only inside the same type of unit (miles to km uses 1 mile = 1.609344 km). km and passenger_km are NOT interchangeable.
3. S2 **picks a factor**: same country and year, else the nearest year in that country, else GLOBAL. Only active factors are used.
4. S2 multiplies: amount x factor. All numbers use `Decimal`, never `float`, so there are no rounding surprises.
5. S2 picks a tariff the same way and computes the cost.
6. S2 stores the result with its trace. If a factor is missing or the unit does not fit, it stores an **error message on the record** and leaves the number empty. It never stores 0.

## 4. Changing factors safely
- A changed factor creates **version + 1**; the old version is deactivated, never deleted (no hard deletes).
- After a change, S2 **recalculates** affected activities. The old results are kept as history (`is_current = False`), the new ones become current.
- `simulate` answers "what if?" and **saves nothing**.

## 5. Where is the code?
| Path | What it does |
|---|---|
| `api/app/engine/core/` | Pure calculation: `units.py` (conversion), `selector.py` (factor/tariff choice), `calculator.py` (the maths), `errors.py`, `types.py`. No database here, so it is easy to test. |
| `api/app/engine/repository.py` | Reads and writes factors, tariffs and results in the database. |
| `api/app/engine/service.py` | Connects everything: calculate, recalculate, simulate. |
| `api/app/engine/importer.py` | Imports factor and tariff CSV files (all or nothing; error per row). |
| `api/app/engine/routes.py` | The API endpoints (below). |
| `api/app/engine/schemas.py` | Shapes of the data going in and out of the API. |
| `seed/` | `factors.csv`, `tariffs.csv`, `run_seed.py` (demo company and starting data). |
| `ui/pages/2_Factors_and_Tariffs.py` | Streamlit page: lists, CSV upload, simulate. |
| `docker-compose.yml`, `api/Dockerfile`, `ui/Dockerfile` | The Docker stack. |
| `.github/workflows/ci.yml` | Automatic tests on every push. |
| `alembic/versions/b7c1d2e3f4a5_...` | Migration: adds the `miles` unit and the green-tariff table. |
| `tests/test_engine/` | 75 tests (calculation core, service, import, API, green tariff). |

## 6. API endpoints (all under `/engine`)
| Method and path | Who | Purpose |
|---|---|---|
| GET `/factors`, GET `/tariffs` | any user | List (filters: type, region, year) |
| POST `/factors`, POST `/tariffs` | admin | Add or update one (creates a new version if it exists) |
| DELETE `/factors/{id}` | admin | Deactivate (soft delete) |
| POST `/factors/import`, `/tariffs/import` | admin | Upload CSV |
| POST `/calculate/{activity_id}` | user | Calculate one activity |
| GET `/results/{activity_id}` | user | Results (`include_history=true` for old ones) |
| POST `/simulate` | user | What-if for a list of items |
| POST `/simulate/compare` | user | Before/after, gives the saving |
| GET / PUT / DELETE `/facilities/{id}/green-tariff` | GET any user, PUT/DELETE admin | A facility's green-tariff factor (market-based Scope 2) |

## 7. CSV formats
Factors: `activity_type,region,year,unit,kg_co2e_per_unit,scope,ghg_category,source`
Tariffs: `activity_type,region,year,unit,eur_per_unit,source`
`source` is required: every number must name where it came from. If one row is wrong the whole file is rejected and the errors are listed.

## 8. Data sources
- Factors: DESNZ (UK government) GHG Conversion Factors 2026, stored as GLOBAL. Electricity: Umweltbundesamt 2024 (0.363 kg/kWh, DE). Each `source` names the sheet and cell.
- Tariffs: electricity BDEW Strompreisanalyse April 2026; diesel and petrol ADAC 21.10.2026. Natural gas and water tariffs are not included (no suitable source yet).

## 9. How to run
1. Get the `.env` file from Tuba and put it in the project root, next to `docker-compose.yml`. Never commit it. It holds `JWT_SECRET`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` and `OPENAI_API_KEY`.
2. `docker compose up --build`. The API container runs the migrations and the seed by itself.
3. API docs: http://localhost:8000/docs. UI: http://localhost:8501. Database port on your PC: 5433.
4. Log in with the demo account that the seed prints in the API log.
5. Optional database viewer: `docker compose --profile tools up` then http://localhost:8080 (System: PostgreSQL, Server: `db`).
6. Fresh start (deletes data; needed after changing the database password): `docker compose down -v`.
7. Tests: `pytest` (Python 3.12 recommended). The app needs `JWT_SECRET` in the environment; CI sets a test value.

## 10. Market-based Scope 2 (green tariff)
- Location-based (grid factor) is always calculated for electricity.
- If the facility has a green-tariff factor (kg CO2e per kWh from the supplier, with a source), a **second result** with `method = market_based` is stored. Cost stays only on the location-based result.
- The location-based result is the main one. Anyone summing results (S3) must not add both: filter on `method`.
- Changing or removing the green tariff recalculates that facility's electricity and keeps the old results as history.

## 11. Known limits
- New activity types (NFR-2.07) are only partly data-driven: a new type needs one list entry, one migration and one factor row.
- Natural gas and water have no tariff yet, so those records get emissions but no cost.
- DESNZ factors are UK-based; they are a fallback, not German values.
- The Streamlit page has its own login box until S3's shell shares its token.
