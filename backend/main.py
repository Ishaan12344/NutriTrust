"""FastAPI entry point for NutriTrust.

HTTP concerns stay here; the product-analysis workflow lives in
``analysis_pipeline`` so it can be reused independently of FastAPI.
"""

import logging

import httpx
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel

from analysis_pipeline import (
    build_ocr_response,
    build_barcode_analysis,
    identity_conflicts as _identity_conflicts,
    scoring_input_from_merged as _scoring_input_from_merged,
)
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


app = FastAPI(
    title="NutriTrust API",
    version="0.1.0",
    description="Food label OCR and Nutrition service with MongoDB integration.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
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


@app.post("/api/v1/ocr")
async def scan_food_label(file: UploadFile = File(...), barcode: str | None = None, username: str | None = None):
    """Validate an upload, run OCR, delegate analysis, and persist scan/product data."""
    logger.info("OCR endpoint started: filename=%s content_type=%s barcode_supplied=%s user=%s", file.filename, file.content_type, bool(barcode), username)
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="Upload a JPG, JPEG or PNG image.")

    try:
        image_bytes = await file.read(MAX_IMAGE_SIZE + 1)
        if not image_bytes:
            raise HTTPException(status_code=400, detail="The uploaded image is empty.")
        if len(image_bytes) > MAX_IMAGE_SIZE:
            raise HTTPException(status_code=413, detail="Image must be 10 MB or smaller.")

        result = await run_in_threadpool(
            extract_text_from_image, image_bytes, file.filename or "food-label.jpg", file.content_type
        )
        logger.info("OCR completed: job_id=%s status=%s text_length=%s", result.get("job_id"), result.get("status"), len(result.get("text") or ""))
        resp = await build_ocr_response(
            ocr_result=result,
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
