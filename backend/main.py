import logging
import re

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from food_data_merger import merge_product_data
from health_analyzer import analyze_product_health
from nutrition_normalizer import normalize_nutrition
from nutrition_parser import parse_food_label
from open_food_facts_service import fetch_open_food_facts_product
from sarvam_ocr import extract_text_from_image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="NutriTrust API",
    version="0.1.0",
    description="Food label OCR service powered by Sarvam AI.",
)

# Development configuration. Restrict origins before production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_TYPES = {"image/jpeg", "image/png"}


def _identity_conflicts(food_label: dict, off_data: dict) -> list[str]:
    """Find contradictions between explicit OCR identity and OFF identity."""
    conflicts = []
    pairs = (
        ("product_name", food_label.get("product_name"), off_data.get("product_name")),
        ("brand", food_label.get("brand"), off_data.get("brands")),
    )
    for field, label_value, off_value in pairs:
        if not isinstance(label_value, str) or not label_value.strip():
            continue
        if not isinstance(off_value, str) or not off_value.strip():
            continue
        label_tokens = set(re.findall(r"[a-z0-9]+", label_value.casefold()))
        off_tokens = set(re.findall(r"[a-z0-9]+", off_value.casefold()))
        if label_tokens and off_tokens and not label_tokens.intersection(off_tokens):
            conflicts.append(field)
    return conflicts


@app.get("/")
def root():
    return {
        "message": "NutriTrust backend is running",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/v1/ocr")
async def scan_food_label(
    file: UploadFile = File(...),
    barcode: str | None = None,
):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail="Upload a JPG, JPEG or PNG image.",
        )

    try:
        image_bytes = await file.read(MAX_IMAGE_SIZE + 1)

        if not image_bytes:
            raise HTTPException(
                status_code=400,
                detail="The uploaded image is empty.",
            )

        if len(image_bytes) > MAX_IMAGE_SIZE:
            raise HTTPException(
                status_code=413,
                detail="Image must be 10 MB or smaller.",
            )

        result = await run_in_threadpool(
            extract_text_from_image,
            image_bytes,
            file.filename or "food-label.jpg",
            file.content_type,
        )

        food_label = parse_food_label(result["text"])
        normalized_nutrition = normalize_nutrition(food_label)

        off_data = None
        integration_warnings = []
        off_request_status = "not_requested"
        identity_match_status = "not_checked"
        merge_off_data = None

        if barcode:
            off_request_status = "found"
            try:
                off_data = await fetch_open_food_facts_product(barcode)

                if not off_data.get("found"):
                    off_request_status = "not_found"
                    identity_match_status = "not_found"
                    integration_warnings.append(
                        off_data.get("message") or "Product was not found in Open Food Facts."
                    )
                else:
                    identity_conflicts = _identity_conflicts(food_label, off_data)
                    has_comparable_identity = any(
                        isinstance(food_label.get(label_key), str)
                        and food_label[label_key].strip()
                        and isinstance(off_data.get(off_key), str)
                        and off_data[off_key].strip()
                        for label_key, off_key in (("product_name", "product_name"), ("brand", "brands"))
                    )
                    if identity_conflicts:
                        identity_match_status = "identity_mismatch"
                        integration_warnings.append(
                            "Open Food Facts identity conflicts with explicit OCR "
                            f"{', '.join(identity_conflicts)}; OFF data is retained separately and excluded from merged product data."
                        )
                    else:
                        identity_match_status = (
                            "matched_by_label" if has_comparable_identity else "barcode_supplied_unverified"
                        )
                        merge_off_data = off_data

            except ValueError as exc:
                off_request_status = "invalid_barcode"
                identity_match_status = "invalid_barcode"
                integration_warnings.append(
                    f"The supplied barcode could not be used: {exc} Continuing with OCR data."
                )

            except httpx.TimeoutException:
                off_request_status = "failed"
                identity_match_status = "lookup_failed"
                integration_warnings.append(
                    "Open Food Facts timed out; continuing with OCR data."
                )

            except (httpx.RequestError, httpx.HTTPStatusError):
                off_request_status = "failed"
                identity_match_status = "lookup_failed"
                integration_warnings.append(
                    "Open Food Facts could not be reached; continuing with OCR data."
                )

            except RuntimeError as exc:
                off_request_status = "failed"
                identity_match_status = "lookup_failed"
                integration_warnings.append(
                    f"Open Food Facts returned unusable data ({exc}); continuing with OCR data."
                )

        merged_product = merge_product_data(
            food_label=food_label,
            normalized_nutrition=normalized_nutrition,
            off_data=merge_off_data,
        )
        health_analysis = analyze_product_health(merged_product)

        missing_data_warnings = []
        if not merged_product["product"].get("name"):
            missing_data_warnings.append("Product name was not identified from the scanned label or Open Food Facts.")
        if not merged_product["ingredients"].get("text"):
            missing_data_warnings.append("Ingredient list is unavailable or unreadable.")
        if not food_label.get("nutrition") and not (
            merge_off_data and merge_off_data.get("nutrition_per_100g")
        ):
            missing_data_warnings.append("No nutrition values were available from OCR or Open Food Facts.")
        allergen_analysis = merged_product["allergens"]["label_analysis"]
        if not allergen_analysis.get("declaration_text"):
            missing_data_warnings.append(
                "No allergen declaration was identified; this does not mean the product is allergen-free."
            )

        ocr_warnings = list(food_label.get("warnings", []))
        if result.get("status") not in {None, "completed"}:
            ocr_warnings.append(f"Sarvam OCR completed with status '{result.get('status')}'; review the extracted text.")

        analysis_warnings = list(dict.fromkeys(
            merged_product["warnings"]
            + normalized_nutrition.get("warnings", [])
            + ocr_warnings
            + integration_warnings
            + missing_data_warnings
            + health_analysis.get("warnings", [])
        ))
        product_analysis = {
            **merged_product,
            "identification": {
                **merged_product["product"],
                "requested_barcode": barcode,
                "requested_barcode_source": "user_input" if barcode else None,
            },
            "ocr": {
                "source": "sarvam_ocr",
                "job_id": result.get("job_id"),
                "status": result.get("status"),
                "extraction_status": food_label.get("extraction", {}).get("status"),
                "warnings": ocr_warnings,
                "normalization_warnings": normalized_nutrition.get("warnings", []),
            },
            "open_food_facts": {
                **merged_product["open_food_facts"],
                "found": bool(off_data and off_data.get("found")),
                "request_status": off_request_status,
                "identity_match_status": identity_match_status,
                "used_for_merge": merge_off_data is not None,
                "source": off_data.get("source") if off_data else None,
                "data": off_data,
                "warning": integration_warnings[0] if integration_warnings else None,
            },
            "conflicts": merged_product["nutrition"]["conflicts"],
            "missing_data_warnings": missing_data_warnings,
            "health_analysis": health_analysis,
            "warnings": analysis_warnings,
            "needs_review": merged_product["needs_review"] or health_analysis["needs_review"] or bool(analysis_warnings),
        }

        return {
            "success": True,
            "filename": file.filename,
            "ocr": {
                "job_id": result["job_id"],
                "status": result["status"],
                "text": result["text"],
            },
            "food_label": food_label,
            "normalized_nutrition": normalized_nutrition,
            "open_food_facts": off_data,
            "merged_product": merged_product,
            "product_analysis": product_analysis,
            "health_analysis": health_analysis,
            "integration_warnings": integration_warnings,
        }

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        logger.warning("OCR processing failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected OCR error")
        raise HTTPException(
            status_code=500,
            detail="Unexpected server error during OCR.",
        ) from exc
    finally:
        await file.close()


@app.get("/api/v1/open-food-facts/{barcode}")
async def get_open_food_facts_product(barcode: str):
    try:
        data = await fetch_open_food_facts_product(barcode)

        return {
            "success": True,
            "data": data,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail="Open Food Facts request timed out.",
        ) from exc

    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Open Food Facts returned HTTP {exc.response.status_code}.",
        ) from exc

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail="Could not connect to Open Food Facts.",
        ) from exc

    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc
