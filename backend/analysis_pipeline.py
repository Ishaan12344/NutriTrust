"""Orchestration for turning OCR and catalog data into an API analysis response.

This module deliberately contains no FastAPI request handling.  Keeping the
pipeline independent of HTTP makes its source-selection and response-building
rules reusable and easier to test without changing the public API contract.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

import httpx


def identity_conflicts(food_label: dict[str, Any], off_data: dict[str, Any]) -> list[str]:
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


def scoring_input_from_merged(merged_product: dict[str, Any]) -> dict[str, Any]:
    """Adapt the unified product model to the scoring service's input schema."""
    nutrition = merged_product.get("nutrition") if isinstance(merged_product.get("nutrition"), dict) else {}
    product = merged_product.get("product") if isinstance(merged_product.get("product"), dict) else {}
    ingredients = merged_product.get("ingredients") if isinstance(merged_product.get("ingredients"), dict) else {}
    classification = merged_product.get("classification") if isinstance(merged_product.get("classification"), dict) else {}
    sources = merged_product.get("data_sources") if isinstance(merged_product.get("data_sources"), dict) else {}
    per_100g = nutrition.get("per_100g") if isinstance(nutrition.get("per_100g"), dict) else {}
    normalization = nutrition.get("ocr_normalization")
    serving_info = normalization.get("serving_size", {}) if isinstance(normalization, dict) else {}
    return {
        "product": product,
        "nutrition_per_100g": per_100g,
        "nutrition_per_serving": nutrition.get("per_serving", {}),
        "ingredients_text": ingredients.get("text"),
        "additives_tags": classification.get("additives_tags", []),
        "additives_count": classification.get("additives_count"),
        "additives_available": sources.get("additives") is not None or bool(
            re.search(r"\bE\s*\d{3,4}[A-Z]?\b", ingredients.get("text") or "", re.IGNORECASE)
        ),
        "nova_group": classification.get("nova_group"),
        "nova_source": sources.get("nova_group"),
        "nutrition_conflicts": nutrition.get("conflicts", []),
        "serving_size_available": bool(serving_info.get("weight_g")),
    }


async def build_ocr_response(
    *,
    ocr_result: dict[str, Any],
    filename: str | None,
    barcode: str | None,
    parse_label: Callable[[str], dict[str, Any]],
    normalize: Callable[[dict[str, Any]], dict[str, Any]],
    fetch_product: Callable[[str], Awaitable[dict[str, Any]]],
    merge_product: Callable[..., dict[str, Any]],
    analyze_health: Callable[[dict[str, Any]], dict[str, Any]],
    score: Callable[[dict[str, Any]], dict[str, Any]],
    logger: logging.Logger,
) -> dict[str, Any]:
    """Build the established OCR endpoint payload from injectable collaborators."""
    logger.info("parsing OCR label")
    food_label = parse_label(ocr_result["text"])
    logger.info("normalizing nutrition")
    normalized_nutrition = normalize(food_label)

    off_data = None
    integration_warnings: list[str] = []
    off_request_status = "not_requested"
    identity_match_status = "not_checked"
    merge_off_data = None

    if barcode:
        logger.info("starting Open Food Facts lookup for supplied barcode")
        off_request_status = "found"
        try:
            off_data = await fetch_product(barcode)
            logger.info("Open Food Facts lookup complete: found=%s", off_data.get("found"))

            if not off_data.get("found"):
                off_request_status = "not_found"
                identity_match_status = "not_found"
                integration_warnings.append(off_data.get("message") or "Product was not found in Open Food Facts.")
            else:
                conflicts = identity_conflicts(food_label, off_data)
                has_comparable_identity = any(
                    isinstance(food_label.get(label_key), str)
                    and food_label[label_key].strip()
                    and isinstance(off_data.get(off_key), str)
                    and off_data[off_key].strip()
                    for label_key, off_key in (("product_name", "product_name"), ("brand", "brands"))
                )
                if conflicts:
                    identity_match_status = "identity_mismatch"
                    integration_warnings.append(
                        "Open Food Facts identity conflicts with explicit OCR "
                        f"{', '.join(conflicts)}; OFF data is retained separately and excluded from merged product data."
                    )
                else:
                    identity_match_status = "matched_by_label" if has_comparable_identity else "barcode_supplied_unverified"
                    if has_comparable_identity:
                        merge_off_data = off_data
                    else:
                        integration_warnings.append(
                            "Open Food Facts data was not merged because the scanned label did not provide a comparable product name or brand for identity verification."
                        )
        except ValueError as exc:
            off_request_status = "invalid_barcode"
            identity_match_status = "invalid_barcode"
            integration_warnings.append(f"The supplied barcode could not be used: {exc} Continuing with OCR data.")
        except httpx.TimeoutException:
            off_request_status = "failed"
            identity_match_status = "lookup_failed"
            integration_warnings.append("Open Food Facts timed out; continuing with OCR data.")
        except (httpx.RequestError, httpx.HTTPStatusError):
            off_request_status = "failed"
            identity_match_status = "lookup_failed"
            integration_warnings.append("Open Food Facts could not be reached; continuing with OCR data.")
        except RuntimeError as exc:
            off_request_status = "failed"
            identity_match_status = "lookup_failed"
            integration_warnings.append(f"Open Food Facts returned unusable data ({exc}); continuing with OCR data.")

    merged_product = merge_product(food_label=food_label, normalized_nutrition=normalized_nutrition, off_data=merge_off_data)
    logger.info("merged OCR and external data")
    health_analysis = analyze_health(merged_product)
    scoring = score(scoring_input_from_merged(merged_product))
    logger.info("NutriTrust score result: eligibility=%s overall=%s", scoring["data_sufficiency"]["scoring_eligibility"], scoring["scores"]["overall"])
    logger.info("health analysis complete: status=%s findings=%s", health_analysis.get("analysis_status"), len(health_analysis.get("findings", [])))

    missing_data_warnings = []
    if not merged_product["product"].get("name"):
        missing_data_warnings.append("Product name was not identified from the scanned label or Open Food Facts.")
    if not merged_product["ingredients"].get("text"):
        missing_data_warnings.append("Ingredient list is unavailable or unreadable.")
    if not food_label.get("nutrition") and not (merge_off_data and merge_off_data.get("nutrition_per_100g")):
        missing_data_warnings.append("No nutrition values were available from OCR or Open Food Facts.")
    allergen_analysis = merged_product["allergens"]["label_analysis"]
    if not allergen_analysis.get("declaration_text"):
        missing_data_warnings.append("No allergen declaration was identified; this does not mean the product is allergen-free.")

    ocr_warnings = list(food_label.get("warnings", []))
    if ocr_result.get("status") not in {None, "completed"}:
        ocr_warnings.append(f"Sarvam OCR completed with status '{ocr_result.get('status')}'; review the extracted text.")
    analysis_warnings = list(dict.fromkeys(
        merged_product["warnings"] + normalized_nutrition.get("warnings", []) + ocr_warnings
        + integration_warnings + missing_data_warnings + health_analysis.get("warnings", [])
    ))
    product_analysis = {
        **merged_product,
        "identification": {**merged_product["product"], "requested_barcode": barcode, "requested_barcode_source": "user_input" if barcode else None},
        "ocr": {"source": "sarvam_ocr", "job_id": ocr_result.get("job_id"), "status": ocr_result.get("status"), "extraction_status": food_label.get("extraction", {}).get("status"), "warnings": ocr_warnings, "normalization_warnings": normalized_nutrition.get("warnings", [])},
        "open_food_facts": {**merged_product["open_food_facts"], "found": bool(off_data and off_data.get("found")), "request_status": off_request_status, "identity_match_status": identity_match_status, "used_for_merge": merge_off_data is not None, "source": off_data.get("source") if off_data else None, "data": off_data, "warning": integration_warnings[0] if integration_warnings else None},
        "conflicts": merged_product["nutrition"]["conflicts"],
        "missing_data_warnings": missing_data_warnings,
        "health_analysis": health_analysis,
        "scoring": scoring,
        "warnings": analysis_warnings,
        "needs_review": merged_product["needs_review"] or health_analysis["needs_review"] or bool(analysis_warnings),
    }
    response_payload = {
        "success": True, "filename": filename,
        "ocr": {"job_id": ocr_result["job_id"], "status": ocr_result["status"], "text": ocr_result["text"]},
        "food_label": food_label, "normalized_nutrition": normalized_nutrition,
        "open_food_facts": off_data, "merged_product": merged_product,
        "product_analysis": product_analysis, "health_analysis": health_analysis,
        "scoring": scoring, "integration_warnings": integration_warnings,
    }
    logger.info("OCR response ready: needs_review=%s warnings=%s", product_analysis["needs_review"], len(analysis_warnings))
    return response_payload


def scoring_input_from_off(data: dict[str, Any]) -> dict[str, Any]:
    """Adapt an Open Food Facts result to the scoring service's input schema."""
    return {
        "product": {"barcode": data.get("barcode"), "name": data.get("product_name"), "brands": data.get("brands"), "categories": data.get("categories")},
        "nutrition_per_100g": data.get("nutrition_per_100g", {}),
        "ingredients_text": data.get("ingredients_text"),
        "additives_tags": data.get("additives_tags", []),
        "additives_count": data.get("additives_count"),
        "additives_available": data.get("additives_available"),
        "nova_group": data.get("nova_group"),
        "nova_source": data.get("nova_source"),
    }


def build_barcode_analysis(
    *,
    off_data: dict[str, Any],
    requested_barcode: str,
    merge_product: Callable[..., dict[str, Any]],
    analyze_health: Callable[[dict[str, Any]], dict[str, Any]],
    score: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    """Build the same unified analysis shape used by the OCR endpoint.

    A barcode lookup has no physical-label evidence, so the empty label below is
    intentional.  The merger then treats Open Food Facts as the sole source and
    retains that provenance on every populated field.
    """
    empty_label = {
        "ingredients": None,
        "ingredient_items": [],
        "product_name": None,
        "brand": None,
        "allergen_analysis": {
            "declared": [], "may_contain": [], "ingredient_terms_detected": [],
            "declaration_text": None, "precautionary_text": None,
            "status": "unknown", "review_required": True,
        },
        "warnings": [],
    }
    empty_normalization = {
        "per_100g": {}, "per_serving": {}, "reference_basis": {"detected": "unknown"},
        "units": {}, "warnings": [],
    }
    merged_product = merge_product(
        food_label=empty_label,
        normalized_nutrition=empty_normalization,
        off_data=off_data,
    )
    health_analysis = analyze_health(merged_product)
    scoring = score(scoring_input_from_merged(merged_product))

    missing_fields = []
    if not merged_product["product"].get("name"):
        missing_fields.append("product_name")
    if not merged_product["nutrition"].get("per_100g"):
        missing_fields.append("nutrition_per_100g")
    if not merged_product["ingredients"].get("text"):
        missing_fields.append("ingredients")
    conflicts = merged_product["nutrition"].get("conflicts", [])
    data_quality_status = "requires_review" if conflicts else ("partial" if missing_fields else "complete")
    warnings = list(dict.fromkeys(
        merged_product["warnings"] + health_analysis.get("warnings", [])
    ))

    return {
        **merged_product,
        "identification": {
            **merged_product["product"],
            "requested_barcode": requested_barcode,
            "requested_barcode_source": "user_input",
        },
        "open_food_facts": {
            **merged_product["open_food_facts"],
            "found": bool(off_data.get("found")),
            "request_status": "found" if off_data.get("found") else "not_found",
            "source": off_data.get("source"),
            "data": off_data,
        },
        "health_analysis": health_analysis,
        "scoring": scoring,
        "data_quality": {
            "status": data_quality_status,
            "missing_fields": missing_fields,
            "conflicts": conflicts,
            "warnings": warnings,
        },
        "missing_data_warnings": [
            f"{field.replace('_', ' ')} is unavailable from Open Food Facts."
            for field in missing_fields
        ],
        "warnings": warnings,
        "needs_review": (
            merged_product["needs_review"]
            or health_analysis["needs_review"]
            or data_quality_status != "complete"
        ),
    }
