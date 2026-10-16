# NutriTrust backend

NutriTrust is a FastAPI service that accepts food-label images and optional
barcodes, combines OCR and Open Food Facts data when their identity agrees,
and returns a Flutter-compatible product analysis.

## Architecture

```text
FastAPI routes (main.py)
  -> OCR + pipeline orchestration (sarvam_ocr.py, analysis_pipeline.py)
  -> parsing and normalization (nutrition_parser.py, nutrition_normalizer.py)
  -> deterministic source merge (food_data_merger.py)
  -> health findings + composite score (health_analyzer.py, scoring_service.py)
```

`open_food_facts_service.py` is a read-only external client and normalizes its
responses before they enter the pipeline. `app_config.py` centralizes
environment-backed limits and timeouts. `data/` contains the local, versioned
additive and NOVA marker references used by the analysis services.

## Requirements and setup

Python 3.12 is the currently verified runtime.

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `SARVAM_API_KEY` in `.env` to enable OCR. Do not commit `.env`. Barcode
lookup and `/health` can start without that key. Optional settings are listed
in `.env.example`, including Open Food Facts and Sarvam timeouts and the upload
size limit.

## Run

```powershell
cd backend
uvicorn main:app --reload
```

OpenAPI documentation is available at `http://127.0.0.1:8000/docs`.

## API contract

The Flutter client uses these endpoints and their existing fields are retained:

- `GET /` — service metadata.
- `GET /health` — `{"status": "ok"}`.
- `POST /api/v1/auth/register` — registers user credentials and personal health profile (name, age, weight, gender, allergies, conditions, preferences) into MongoDB.
- `POST /api/v1/auth/login` — authenticates user credentials against MongoDB and returns user profile.
- `GET /api/v1/user/profile` — retrieves saved health profile from MongoDB.
- `PUT /api/v1/user/profile` — updates personal health profile in MongoDB.
- `POST /api/v1/ocr` — multipart field `file` (`image/jpeg` or `image/png`),
  with optional `barcode`. Returns `success`, OCR output, parsed label,
  normalized nutrition, merged product, `product_analysis`, health analysis,
  scoring, and integration warnings.
- `GET /api/v1/open-food-facts/{barcode}` — returns `success`, normalized
  Open Food Facts `data`, `scoring`, and a canonical `product_analysis`. The
  latter includes field provenance, data-quality status, independent health
  findings, and the same score object; `data` and `scoring` remain for existing
  Flutter clients.

Example label request:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/ocr -F "file=@label.png;type=image/png" -F "barcode=3017624010701"
```

## Data and scoring rules

OCR values stay separate from normalized values. Unit conversions occur only
when the source basis and units are explicit. Missing, ambiguous, and
implausible values remain missing or are marked for review; they are never
silently converted to zero.

The merge layer records a source for fields and preserves nutrition conflicts.
OCR and Open Food Facts records are merged only when explicit name or brand
tokens do not conflict. The detailed composite-score formula, source limits,
and limitations are documented in [SCORING_POLICY.md](SCORING_POLICY.md).
NutriTrust component scores are not official Nutri-Score classifications or
medical advice.

## Tests

Tests mock OCR and Open Food Facts calls; they do not require a network request
or a real OCR key.

```powershell
cd backend
python -m unittest discover -v
```

The suite covers parsing, unit conversion, source merging, score eligibility,
external lookup failures, endpoint payloads, and Flutter-required response
fields.

## Troubleshooting

- `SARVAM_API_KEY is missing`: copy `.env.example` to `.env` and configure the
  key before using the OCR endpoint.
- Barcode lookup timeout: retry later; OCR-only analysis remains available.
- Android emulator: start Flutter with
  `--dart-define=NUTRITRUST_API_BASE_URL=http://10.0.2.2:8000`.
- Physical Android device: use `adb reverse tcp:8000 tcp:8000`, or start the
  backend on a reachable LAN interface and pass its address with
  `--dart-define=NUTRITRUST_API_BASE_URL=http://192.168.x.x:8000`.
