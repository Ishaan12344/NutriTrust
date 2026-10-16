"""FastAPI entry point for NutriTrust.

HTTP concerns stay here; the product-analysis workflow lives in
``analysis_pipeline`` so it can be reused independently of FastAPI.
"""

import logging

import httpx
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from analysis_pipeline import (
    build_ocr_response,
    build_barcode_analysis,
    identity_conflicts as _identity_conflicts,
    scoring_input_from_merged as _scoring_input_from_merged,
)
from app_config import get_settings
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

app = FastAPI(
    title="NutriTrust API",
    version="0.1.0",
    description="Food label OCR service powered by Sarvam AI.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
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


@app.post("/api/v1/ocr")
async def scan_food_label(file: UploadFile = File(...), barcode: str | None = None):
    """Validate an upload, run OCR, and delegate analysis construction to the pipeline."""
    logger.info("OCR endpoint started: filename=%s content_type=%s barcode_supplied=%s", file.filename, file.content_type, bool(barcode))
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
        return await build_ocr_response(
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
async def get_open_food_facts_product(barcode: str):
    logger.info("barcode endpoint started: barcode_length=%s", len(barcode))
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
        return {
            "success": True,
            "data": data,
            "scoring": product_analysis["scoring"],
            "product_analysis": product_analysis,
        }
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
