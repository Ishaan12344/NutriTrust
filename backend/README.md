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
  -> independent food-intelligence engines
     (nutri_score_engine.py, nova_engine.py, additive_regulatory_engine.py)
  -> optional local-LLM summary (summary_service.py)
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
- `POST /api/v1/manual-assessment` — JSON body with manually supplied product data (name, category, ingredients, per-100 nutrients and optional additive concentrations). Returns the same three engine results and unified analysis shape as the scan endpoints.
- `POST /api/v1/summary` — natural-language summary of a scan for one user.
  Body: `{"username": "...", "product_analysis": {...}}`. The user's saved
  health profile is looked up server-side and combined with the product facts,
  health findings, and score. Returns `{"success", "status", "summary",
  "source", "model", "prompt_version"}` where `source` is `model` or
  `fallback`. The endpoint never fails because of the model: it always returns
  text to show, and never breaks the scan endpoints.

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

The independent Nutri-Score, NOVA, and FSSAI additive engines, their versioned rules, and their limitations are documented in [FOOD_INTELLIGENCE_REFERENCES.md](FOOD_INTELLIGENCE_REFERENCES.md).

## Summary model

`POST /api/v1/summary` uses the instruction-tuned Qwen2.5-1.5B model bundled in
`models/Qwen2.5-1.5B-Instruct`. It is loaded lazily on the first request (about
4-5 s on CPU) and reused afterwards; generation is serialized and bounded by
`NUTRITRUST_SUMMARY_MAX_NEW_TOKENS`. On CPU, expect roughly 10-30 s per summary.

The prompt contains only data the pipeline already produced plus the user's
saved profile, and the model is instructed not to invent values, to state what
is unknown, and not to give medical advice. Set
`NUTRITRUST_SUMMARY_ENABLED=false` to disable the endpoint, or point
`NUTRITRUST_SUMMARY_MODEL_PATH` at another compatible local model directory.

### Incomplete product data

Barcode lookups often return partial or empty Open Food Facts records. The
summary is built so this never produces a blank result or an invented one:

- If the analysis has no nutrition, ingredient, or allergen data at all, no
  generation is attempted. A deterministic summary is returned instead
  (`source: "fallback"`), stating what could not be scored and what is missing.
  This also keeps a not-found barcode fast: about 20 ms rather than 20 s.
- When at least some data exists, the model writes the summary, and the prompt
  marks every missing fact as `not available`.
- The result is then checked against the pipeline's facts. A summary is
  rejected, and replaced by the deterministic fallback, when it claims the
  presence or absence of an allergen with no matching allergen data, calls a
  product allergen-free, or describes a nutrient band for a nutrient that was
  never measured. A 1.5B model does all four on sparse input.
- A model error, timeout, or empty output also falls back, so the response
  always carries text. Only `NUTRITRUST_SUMMARY_ENABLED=false` returns no
  summary.

On the Flutter side, no report section is dropped when data is missing: the
nutrition sections stay visible and say the values were not found, and the AI
Summary card shows whatever the endpoint returned.

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
