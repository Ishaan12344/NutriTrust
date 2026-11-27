"""FastAPI entry point for NutriTrust.

HTTP concerns stay here; the product-analysis workflow lives in
``analysis_pipeline`` so it can be reused independently of FastAPI.
"""

import asyncio
import logging
from datetime import date as date_cls
from functools import partial
from typing import Any

import httpx
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel

from analysis_pipeline import build_barcode_analysis, build_manual_analysis, build_ocr_response
from app_config import get_settings
from database import (
    authenticate_user,
    get_profile,
    get_user_scans,
    register_user,
    save_scan_and_product,
    update_profile,
)
from food_data_merger import merge_product_data
from health_analyzer import analyze_product_health
from nutrition_normalizer import normalize_nutrition
from nutrition_parser import parse_food_label
from open_food_facts_service import fetch_open_food_facts_product
from sarvam_ocr import extract_text_from_image
from scoring_service import rate
from tracker_service import (
    add_tracker_item,
    delete_tracker_item,
    get_tracker_snapshot,
    update_tracker_item,
)
from summary_service import (
    generate_text as _generate_summary_text,
    summarize_analysis as _summarize_analysis,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_IMAGE_SIZE = get_settings().max_image_size_bytes
ALLOWED_TYPES = {"image/jpeg", "image/png"}


class RegisterRequest(BaseModel):
    username: str
    password: str
    name: str | None = None
    age: int | None = None
    weight: float | None = None
    gender: str | None = None
    allergies: list[str] = []
    allergy_other: str | None = None
    conditions: list[str] = []
    condition_other: str | None = None
    preferences: list[str] = []


class LoginRequest(BaseModel):
    username: str
    password: str


class ProfileUpdateRequest(BaseModel):
    username: str
    name: str | None = None
    age: int | None = None
    weight: float | None = None
    gender: str | None = None
    allergies: list[str] = []
    allergy_other: str | None = None
    conditions: list[str] = []
    condition_other: str | None = None
    preferences: list[str] = []


class SummaryRequest(BaseModel):
    """Input for the optional local-LLM summary.

    ``product_analysis`` is the payload returned by the scan endpoints.  The
    top-level ``scoring`` and ``health_analysis`` fields are accepted as
    fallbacks for callers that send them separately.
    """

    username: str | None = None
    product_analysis: dict[str, Any] | None = None
    scoring: dict[str, Any] | None = None
    health_analysis: dict[str, Any] | None = None


class TrackerItemRequest(BaseModel):
    """A scanned item entering the tracker, with its validated nutrition values."""

    username: str | None = None
    date: str | None = None
    name: str | None = None
    brand: str | None = None
    barcode: str | None = None
    image_url: str | None = None
    source: str = "scan"
    manual_name: bool = False
    nutrition: dict[str, float | None] = {}
    nutrition_basis: str = "per_serving"
    allergens: list[str] = []
    additives: list[str] = []
    nutri_grade: str | None = None
    health_score: float | None = None


class TrackerItemUpdateRequest(BaseModel):
    username: str | None = None
    status: str | None = None
    name: str | None = None


class ManualAssessmentRequest(BaseModel):
    """Manually supplied product data; all nutrition values are per 100 g/100 ml."""

    username: str | None = None
    product_name: str | None = None
    brand: str | None = None
    category: str | None = None
    ingredients_text: str | None = None
    additives: list[str] = []
    additive_concentrations: dict[str, dict[str, Any]] = {}
    energy_kcal_per_100g: float | None = None
    total_fat_per_100g: float | None = None
    saturated_fat_per_100g: float | None = None
    sugars_per_100g: float | None = None
    fiber_per_100g: float | None = None
    protein_per_100g: float | None = None
    sodium_mg_per_100g: float | None = None
    salt_g_per_100g: float | None = None
    fruit_vegetable_percent: float | None = None
    non_nutritive_sweeteners: bool | None = None


app = FastAPI(
    title="NutriTrust API",
    version="0.1.0",
    description="Food label OCR and Nutrition service with MongoDB integration.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    logger.info("incoming request: %s %s", request.method, request.url.path)
    try:
        response = await call_next(request)
        logger.info("request complete: %s %s -> %s", request.method, request.url.path, response.status_code)
        return response
    except Exception:
        logger.exception("request failed: %s %s", request.method, request.url.path)
        raise


@app.get("/")
def root():
    return {"message": "NutriTrust backend is running", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/v1/auth/register")
def register(req: RegisterRequest):
    """Register a new user in MongoDB with health profile data."""
    try:
        user_data = register_user(
            username=req.username,
            password=req.password,
            profile_data=req.model_dump(),
        )
        return {"success": True, "message": "User registered successfully", "user": user_data}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/v1/auth/login")
def login(req: LoginRequest):
    """Authenticate a user and return their saved health profile."""
    try:
        user_data = authenticate_user(username=req.username, password=req.password)
        return {"success": True, "message": "Login successful", "user": user_data}
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/v1/user/profile")
def fetch_user_profile(username: str):
    """Fetch health profile from MongoDB for a given username."""
    try:
        profile = get_profile(username=username)
        return {"success": True, "profile": profile}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.put("/api/v1/user/profile")
def save_user_profile(req: ProfileUpdateRequest):
    """Update health profile in MongoDB (name, age, weight, gender, allergies, etc.)."""
    try:
        profile = update_profile(username=req.username, profile_data=req.model_dump())
        return {"success": True, "profile": profile}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc



@app.get("/api/v1/user/scans")
def fetch_user_scans(username: str):
    """Retrieve scan history for a user from MongoDB."""
    return {"success": True, "scans": get_user_scans(username=username)}


@app.get("/api/v1/tracker")
def fetch_tracker(
    username: str | None = None,
    period: str = "daily",
    date: str | None = None,
):
    """Return tracked items, intake totals and suggestions for one period."""
    try:
        anchor = date_cls.fromisoformat(date) if date else date_cls.today()
        return get_tracker_snapshot(username, period, anchor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/tracker/items")
def create_tracker_item(req: TrackerItemRequest):
    """Add a scanned item to the tracker; pending until the user marks it."""
    return {"success": True, "item": add_tracker_item(req.model_dump())}


@app.patch("/api/v1/tracker/items/{item_id}")
def patch_tracker_item(item_id: str, req: TrackerItemUpdateRequest):
    """Update an item's consumption status or user-supplied name."""
    try:
        item = update_tracker_item(item_id, req.username, req.model_dump(exclude_none=True))
        return {"success": True, "item": item}
    except ValueError as exc:
        code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@app.delete("/api/v1/tracker/items/{item_id}")
def remove_tracker_item(item_id: str, username: str | None = None):
    """Remove an item the user did not eat."""
    try:
        delete_tracker_item(item_id, username)
        return {"success": True}
    except ValueError as exc:
        code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@app.post("/api/v1/ocr")
async def scan_food_label(
    file: UploadFile = File(...),
    ingredients_file: UploadFile | None = File(None),
    barcode: str | None = None,
    username: str | None = None,
):
    """Validate an upload, run OCR, delegate analysis, and persist scan/product data.

    ``file`` is the nutrition-label photo.  ``ingredients_file`` is an optional
    second photo of the ingredients list, used to improve ingredient, allergen
    and additive extraction.
    """
    logger.info(
        "OCR endpoint started: filename=%s content_type=%s ingredients_supplied=%s barcode_supplied=%s user=%s",
        file.filename, file.content_type, bool(ingredients_file), bool(barcode), username,
    )

    async def read_upload(upload: UploadFile) -> bytes:
        if upload.content_type not in ALLOWED_TYPES:
            raise HTTPException(status_code=415, detail="Upload a JPG, JPEG or PNG image.")
        data = await upload.read(MAX_IMAGE_SIZE + 1)
        if not data:
            raise HTTPException(status_code=400, detail="The uploaded image is empty.")
        if len(data) > MAX_IMAGE_SIZE:
            raise HTTPException(status_code=413, detail="Image must be 10 MB or smaller.")
        return data

    async def ocr_optional_ingredients(image_bytes: bytes) -> dict[str, Any]:
        # A failed optional ingredients photo must not fail the whole scan;
        # the analysis continues from the nutrition photo with a visible warning.
        try:
            return await run_in_threadpool(
                extract_text_from_image,
                image_bytes,
                ingredients_file.filename or "ingredients.jpg",
                ingredients_file.content_type,
            )
        except Exception as exc:
            logger.warning("Ingredients photo OCR failed; continuing without it: %s", exc)
            return {"job_id": None, "status": "failed", "text": "", "error": str(exc)}

    try:
        image_bytes = await read_upload(file)
        ingredients_bytes = await read_upload(ingredients_file) if ingredients_file else None

        nutrition_task = run_in_threadpool(
            extract_text_from_image, image_bytes, file.filename or "food-label.jpg", file.content_type
        )
        if ingredients_file and ingredients_bytes is not None:
            result, ingredients_result = await asyncio.gather(
                nutrition_task, ocr_optional_ingredients(ingredients_bytes)
            )
        else:
            result = await nutrition_task
            ingredients_result = None

        logger.info("OCR completed: job_id=%s status=%s text_length=%s", result.get("job_id"), result.get("status"), len(result.get("text") or ""))
        if ingredients_result:
            logger.info("Ingredients OCR completed: job_id=%s status=%s text_length=%s", ingredients_result.get("job_id"), ingredients_result.get("status"), len(ingredients_result.get("text") or ""))
        resp = await build_ocr_response(
            ocr_result=result,
            ingredients_ocr_result=ingredients_result,
            filename=file.filename,
            barcode=barcode,
            parse_label=parse_food_label,
            normalize=normalize_nutrition,
            fetch_product=fetch_open_food_facts_product,
            merge_product=merge_product_data,
            analyze_health=analyze_product_health,
            score=rate,
            logger=logger,
        )
        try:
            save_scan_and_product(
                scan_type="ocr",
                analysis_response=resp,
                username=username,
                barcode=barcode,
            )
        except Exception as exc:
            logger.warning("Could not persist OCR scan: %s", exc)
        return resp
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.warning("OCR processing failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected OCR error")
        raise HTTPException(status_code=500, detail="Unexpected server error during OCR.") from exc
    finally:
        await file.close()
        if ingredients_file:
            await ingredients_file.close()



@app.post("/api/v1/manual-assessment")
async def manual_assessment(req: ManualAssessmentRequest):
    """Run the same assessment engines on manually entered product data."""
    payload = req.model_dump() if hasattr(req, "model_dump") else req.dict()
    logger.info(
        "manual assessment started: name=%s category_supplied=%s user=%s",
        payload.get("product_name"), bool(payload.get("category")), payload.get("username"),
    )
    product_analysis = build_manual_analysis(
        payload=payload,
        merge_product=merge_product_data,
        analyze_health=analyze_product_health,
        score=rate,
        logger=logger,
    )
    resp = {
        "success": True,
        "product_analysis": product_analysis,
        "nutri_score": product_analysis["nutri_score"],
        "nova": product_analysis["nova"],
        "additive_regulatory": product_analysis["additive_regulatory"],
    }
    try:
        save_scan_and_product(
            scan_type="manual",
            analysis_response=resp,
            username=payload.get("username"),
        )
    except Exception as exc:
        logger.warning("Could not persist manual assessment: %s", exc)
    return resp


@app.get("/api/v1/open-food-facts/{barcode}")
async def get_open_food_facts_product(barcode: str, username: str | None = None):
    logger.info("barcode endpoint started: barcode_length=%s user=%s", len(barcode), username)
    try:
        data = await fetch_open_food_facts_product(barcode)
        logger.info("barcode endpoint lookup complete: found=%s", data.get("found"))
        product_analysis = build_barcode_analysis(
            off_data=data,
            requested_barcode=barcode,
            merge_product=merge_product_data,
            analyze_health=analyze_product_health,
            score=rate,
        )
        resp = {
            "success": True,
            "data": data,
            "scoring": product_analysis["scoring"],
            "product_analysis": product_analysis,
        }
        try:
            save_scan_and_product(
                scan_type="barcode",
                analysis_response=resp,
                username=username,
                barcode=barcode,
            )
        except Exception as exc:
            logger.warning("Could not persist barcode scan: %s", exc)
        return resp
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Open Food Facts request timed out.") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Open Food Facts returned HTTP {exc.response.status_code}.") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="Could not connect to Open Food Facts.") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _summary_input(req: SummaryRequest) -> dict[str, Any]:
    """Normalize a summary request into the product-analysis shape."""
    analysis = dict(req.product_analysis) if isinstance(req.product_analysis, dict) else {}
    if req.scoring and "scoring" not in analysis:
        analysis["scoring"] = req.scoring
    if req.health_analysis and "health_analysis" not in analysis:
        analysis["health_analysis"] = req.health_analysis
    return analysis


@app.post("/api/v1/summary")
async def summarize_product(req: SummaryRequest):
    """Summarize a scan for a user with the bundled local model (best-effort).

    A disabled, unavailable, or timed-out model returns ``success: false`` with
    a ``status`` reason rather than failing the request, so the scan pipeline
    and its response contract are never broken by the summarizer.
    """
    settings = get_settings()
    analysis = _summary_input(req)
    if not analysis:
        raise HTTPException(
            status_code=422,
            detail="Product analysis data is required to build a summary.",
        )

    if not settings.summary_enabled:
        return {"success": False, "status": "disabled", "summary": None, "model": None}

    profile: dict[str, Any] = {}
    if req.username and req.username.strip():
        try:
            profile = get_profile(username=req.username)
        except (ValueError, RuntimeError) as exc:
            logger.info("summary profile lookup skipped for %s: %s", req.username, exc)

    logger.info("summary endpoint started: user=%s has_profile=%s", req.username, bool(profile))
    result = await run_in_threadpool(
        _summarize_analysis,
        profile,
        analysis,
        generate=partial(
            _generate_summary_text,
            model_path=settings.summary_model_path,
            timeout_seconds=settings.summary_timeout_seconds,
        ),
        max_new_tokens=settings.summary_max_new_tokens,
    )
    logger.info("summary endpoint complete: status=%s", result.get("status"))
    return {"success": result["status"] == "ok", **result}
