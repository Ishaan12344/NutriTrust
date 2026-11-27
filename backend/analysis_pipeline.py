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

from additive_regulatory_engine import assess_additives
from nova_engine import classify_nova
from nutri_score_engine import calculate_nutri_score

_LOGGER = logging.getLogger(__name__)


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


def food_intelligence_inputs_from_merged(
    merged_product: dict[str, Any],
    overrides: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build the three engines' inputs from the one canonical merged product."""
    product = merged_product.get("product") if isinstance(merged_product.get("product"), dict) else {}
    nutrition = merged_product.get("nutrition") if isinstance(merged_product.get("nutrition"), dict) else {}
    ingredients = merged_product.get("ingredients") if isinstance(merged_product.get("ingredients"), dict) else {}
    classification = merged_product.get("classification") if isinstance(merged_product.get("classification"), dict) else {}
    sources = merged_product.get("data_sources") if isinstance(merged_product.get("data_sources"), dict) else {}
    per_100g = nutrition.get("per_100g") if isinstance(nutrition.get("per_100g"), dict) else {}

    def nutrient(key: str) -> Any:
        item = per_100g.get(key)
        return item.get("value") if isinstance(item, dict) else None

    category = product.get("categories") or product.get("name")
    additives_tags = classification.get("additives_tags") or []
    ingredients_text = ingredients.get("text")
    additive_data_available = sources.get("additives") is not None or bool(
        re.search(r"\bE\s*\d{3,4}[A-Z]?\b", ingredients_text or "", re.IGNORECASE)
    )
    base = {
        "name": product.get("name"),
        "category": category,
        "ingredients_text": ingredients_text,
        "additives_tags": additives_tags,
    }
    nutri_input = {
        **base,
        "energy_kcal": nutrient("energy_kcal"),
        "energy_kj": nutrient("energy_kj"),
        "sugars": nutrient("sugar"),
        "saturated_fat": nutrient("saturated_fat"),
        "total_fat": nutrient("total_fat"),
        "sodium_mg": nutrient("sodium"),
        "salt": nutrient("salt"),
        "fibre": nutrient("fiber"),
        "protein": nutrient("protein"),
    }
    nova_input = {
        **base,
        "ingredient_items": ingredients.get("items") or [],
        "nova_group": classification.get("nova_group"),
        "nova_source": sources.get("nova_group"),
    }
    additive_input = {
        **base,
        "additives_available": additive_data_available,
        "additive_concentrations": {},
    }
    overrides = overrides or {}
    nutri_input.update(overrides.get("nutri_score") or {})
    nova_input.update(overrides.get("nova") or {})
    additive_input.update(overrides.get("additive_regulatory") or {})
    return {
        "nutri_score": nutri_input,
        "nova": nova_input,
        "additive_regulatory": additive_input,
    }


def _safe_engine(name: str, engine: Callable[[dict[str, Any]], dict[str, Any]], payload: dict[str, Any], log: logging.Logger) -> dict[str, Any]:
    """Run one engine without letting its failure affect the other assessments."""
    try:
        return engine(payload)
    except Exception as exc:
        log.warning("%s engine failed; continuing with other assessments: %s", name, exc)
        return {
            "status": "engine_error",
            "error": str(exc),
            "warning": f"The {name} assessment could not be completed; other assessments were unaffected.",
        }


def run_food_intelligence(
    merged_product: dict[str, Any],
    *,
    log: logging.Logger | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Run the three independent engines over the canonical product model."""
    log = log or _LOGGER
    inputs = food_intelligence_inputs_from_merged(merged_product, overrides)
    return {
        "nutri_score": _safe_engine("Nutri-Score", calculate_nutri_score, inputs["nutri_score"], log),
        "nova": _safe_engine("NOVA", classify_nova, inputs["nova"], log),
        "additive_regulatory": _safe_engine("additive regulatory", assess_additives, inputs["additive_regulatory"], log),
    }


def _merge_unique(*values: Any) -> list[Any]:
    merged: list[Any] = []
    for items in values:
        for item in items or []:
            if item not in merged:
                merged.append(item)
    return merged


def _merge_label_sources(
    primary_label: dict[str, Any],
    ingredients_label: dict[str, Any],
    nutrition_label: dict[str, Any],
) -> dict[str, Any]:
    """Combine the nutrition-label and ingredients-label parses into one label.

    ``nutrition_label`` is whichever parse supplied the nutrition values; the
    remaining fields prefer the ingredients photo, then the nutrition photo.
    """
    merged = dict(nutrition_label)
    merged["ingredients"] = ingredients_label.get("ingredients") or primary_label.get("ingredients")
    merged["ingredient_items"] = (
        ingredients_label.get("ingredient_items")
        or primary_label.get("ingredient_items")
        or []
    )
    merged["product_name"] = primary_label.get("product_name") or ingredients_label.get("product_name")
    merged["brand"] = primary_label.get("brand") or ingredients_label.get("brand")
    # Additives are declared on the ingredient list, not the nutrition table.
    # Use only the ingredients label's additives_tags to avoid false positives
    # from nutrition information (e.g., "100 g" being interpreted as E100).
    merged["additives_tags"] = ingredients_label.get("additives_tags") or primary_label.get("additives_tags")

    primary_allergens = primary_label.get("allergen_analysis") or {}
    ingredients_allergens = ingredients_label.get("allergen_analysis") or {}
    declared = _merge_unique(
        primary_allergens.get("declared"), ingredients_allergens.get("declared")
    )
    may_contain = _merge_unique(
        primary_allergens.get("may_contain"), ingredients_allergens.get("may_contain")
    )
    declaration_text = (
        ingredients_allergens.get("declaration_text")
        or primary_allergens.get("declaration_text")
    )
    precautionary_text = (
        ingredients_allergens.get("precautionary_text")
        or primary_allergens.get("precautionary_text")
    )
    if declaration_text is not None or precautionary_text is not None:
        status = "declared_on_label"
    elif merged["ingredients"]:
        status = "ingredient_terms_detected"
    else:
        status = "unknown"
    merged["allergen_analysis"] = {
        "declared": declared,
        "may_contain": may_contain,
        "ingredient_terms_detected": _merge_unique(
            primary_allergens.get("ingredient_terms_detected"),
            ingredients_allergens.get("ingredient_terms_detected"),
        ),
        "declaration_text": declaration_text,
        "precautionary_text": precautionary_text,
        "status": status,
        "review_required": (
            status == "unknown"
            or (declaration_text is not None and not declared)
            or (precautionary_text is not None and not may_contain)
        ),
    }
    merged["allergens"] = declaration_text or precautionary_text
    merged["warnings"] = _merge_unique(
        primary_label.get("warnings"), ingredients_label.get("warnings")
    )
    return merged


async def build_ocr_response(
    *,
    ocr_result: dict[str, Any],
    filename: str | None,
    barcode: str | None,
    parse_label: Callable[..., dict[str, Any]],
    normalize: Callable[[dict[str, Any]], dict[str, Any]],
    fetch_product: Callable[[str], Awaitable[dict[str, Any]]],
    merge_product: Callable[..., dict[str, Any]],
    analyze_health: Callable[[dict[str, Any]], dict[str, Any]],
    score: Callable[[dict[str, Any]], dict[str, Any]],
    logger: logging.Logger,
    ingredients_ocr_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the established OCR endpoint payload from injectable collaborators."""
    logger.info("parsing OCR label")
    primary_label = parse_label(ocr_result["text"])
    ingredients_label = (
        parse_label(ingredients_ocr_result["text"], ingredients_only=True)
        if ingredients_ocr_result
        else None
    )
    nutrition_label = primary_label
    nutrition_source = "nutrition_label"
    if ingredients_label and not (
        primary_label.get("nutrition") or primary_label.get("calories_per_serving_kcal")
    ):
        nutrition_label = ingredients_label
        nutrition_source = "ingredients_label"
    food_label = (
        _merge_label_sources(primary_label, ingredients_label, nutrition_label)
        if ingredients_label
        else primary_label
    )
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
    food_intelligence = run_food_intelligence(merged_product, log=logger)
    health_analysis = analyze_health(merged_product, engine_results=food_intelligence)
    scoring = score(scoring_input_from_merged(merged_product))
    logger.info("NutriTrust score result: eligibility=%s overall=%s", scoring["data_sufficiency"]["scoring_eligibility"], scoring["scores"]["overall"])
    logger.info("food intelligence: nutri_score=%s nova=%s additives=%s", food_intelligence["nutri_score"].get("status"), food_intelligence["nova"].get("status"), food_intelligence["additive_regulatory"].get("overall_status"))
    logger.info("health analysis complete: status=%s findings=%s", health_analysis.get("analysis_status"), len(health_analysis.get("findings", [])))

    ocr_warnings = list(food_label.get("warnings", []))
    if ocr_result.get("status") not in {None, "completed"}:
        ocr_warnings.append(f"Sarvam OCR completed with status '{ocr_result.get('status')}'; review the extracted text.")
    if ingredients_ocr_result and ingredients_ocr_result.get("status") not in {None, "completed"}:
        ocr_warnings.append(f"Ingredients photo OCR completed with status '{ingredients_ocr_result.get('status')}'; review the extracted text.")
    if nutrition_source == "ingredients_label":
        ocr_warnings.append("Nutrition values were taken from the ingredients-list photo because the nutrition photo contained none.")
    engine_warnings = [
        result["warning"] for result in food_intelligence.values()
        if isinstance(result, dict) and result.get("status") == "engine_error" and result.get("warning")
    ]
    # Missing fields are represented by unavailable values in their own cards;
    # they are not user-facing warnings.  Keep warnings for actual processing,
    # identity, or engine failures only.
    analysis_warnings = list(dict.fromkeys(
        merged_product["warnings"] + normalized_nutrition.get("warnings", []) + ocr_warnings
        + integration_warnings + engine_warnings
    ))
    official_nutri = food_intelligence["nutri_score"]
    classification = dict(merged_product["classification"])
    classification["nutriscore"] = {
        **(merged_product["classification"].get("nutriscore") or {}),
        "reported_grade": merged_product["classification"].get("nutriscore_grade"),
        "calculated_status": official_nutri.get("status"),
        "algorithm_version": official_nutri.get("algorithm_version"),
        "score": official_nutri.get("score"),
        "grade": official_nutri.get("grade"),
        "note": "Official updated Nutri-Score result is in nutri_score; the separate scoring component remains a NutriTrust composite.",
    }
    product_analysis = {
        **merged_product,
        "classification": classification,
        "nutri_score": official_nutri,
        "nova": food_intelligence["nova"],
        "additive_regulatory": food_intelligence["additive_regulatory"],
        "identification": {**merged_product["product"], "requested_barcode": barcode, "requested_barcode_source": "user_input" if barcode else None},
        "ocr": {"source": "sarvam_ocr", "job_id": ocr_result.get("job_id"), "status": ocr_result.get("status"), "extraction_status": food_label.get("extraction", {}).get("status"), "ingredients_job_id": ingredients_ocr_result.get("job_id") if ingredients_ocr_result else None, "ingredients_status": ingredients_ocr_result.get("status") if ingredients_ocr_result else None, "ingredients_extraction_status": ingredients_label.get("extraction", {}).get("status") if ingredients_label else None, "nutrition_source": nutrition_source, "warnings": ocr_warnings, "normalization_warnings": normalized_nutrition.get("warnings", [])},
        "open_food_facts": {**merged_product["open_food_facts"], "found": bool(off_data and off_data.get("found")), "request_status": off_request_status, "identity_match_status": identity_match_status, "used_for_merge": merge_off_data is not None, "source": off_data.get("source") if off_data else None, "data": off_data, "warning": integration_warnings[0] if integration_warnings else None},
        "conflicts": merged_product["nutrition"]["conflicts"],
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
        "nutri_score": official_nutri,
        "nova": food_intelligence["nova"],
        "additive_regulatory": food_intelligence["additive_regulatory"],
    }
    if ingredients_ocr_result:
        response_payload["ocr_ingredients"] = {
            "job_id": ingredients_ocr_result["job_id"],
            "status": ingredients_ocr_result["status"],
            "text": ingredients_ocr_result["text"],
        }
        response_payload["ingredients_food_label"] = ingredients_label

    logger.info("OCR response ready: needs_review=%s warnings=%s", product_analysis["needs_review"], len(analysis_warnings))
    return response_payload


def build_barcode_analysis(
    *,
    off_data: dict[str, Any],
    requested_barcode: str,
    merge_product: Callable[..., dict[str, Any]],
    analyze_health: Callable[[dict[str, Any]], dict[str, Any]],
    score: Callable[[dict[str, Any]], dict[str, Any]],
    logger: logging.Logger | None = None,
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
    food_intelligence = run_food_intelligence(merged_product, log=logger or _LOGGER)
    health_analysis = analyze_health(merged_product, engine_results=food_intelligence)
    scoring = score(scoring_input_from_merged(merged_product))

    missing_fields = []
    if not merged_product["product"].get("name"):
        missing_fields.append("product_name")
    if not merged_product["nutrition"].get("per_100g"):
        missing_fields.append("nutrition_per_100g")
    if not merged_product["ingredients"].get("text"):
        missing_fields.append("ingredients")
    conflicts = merged_product["nutrition"].get("conflicts", [])
    engine_warnings = [
        result["warning"] for result in food_intelligence.values()
        if isinstance(result, dict) and result.get("status") == "engine_error" and result.get("warning")
    ]
    warnings = list(dict.fromkeys(
        merged_product["warnings"] + health_analysis.get("warnings", []) + engine_warnings
    ))
    official_nutri = food_intelligence["nutri_score"]
    classification = dict(merged_product["classification"])
    classification["nutriscore"] = {
        **(merged_product["classification"].get("nutriscore") or {}),
        "reported_grade": merged_product["classification"].get("nutriscore_grade"),
        "calculated_status": official_nutri.get("status"),
        "algorithm_version": official_nutri.get("algorithm_version"),
        "score": official_nutri.get("score"),
        "grade": official_nutri.get("grade"),
        "note": "Official updated Nutri-Score result is in nutri_score; the separate scoring component remains a NutriTrust composite.",
    }

    return {
        **merged_product,
        "classification": classification,
        "nutri_score": official_nutri,
        "nova": food_intelligence["nova"],
        "additive_regulatory": food_intelligence["additive_regulatory"],
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
        "warnings": warnings,
        "needs_review": (
            merged_product["needs_review"]
            or health_analysis["needs_review"]
            or bool(missing_fields)
        ),
    }


def build_manual_analysis(
    *,
    payload: dict[str, Any],
    merge_product: Callable[..., dict[str, Any]],
    analyze_health: Callable[[dict[str, Any]], dict[str, Any]],
    score: Callable[[dict[str, Any]], dict[str, Any]],
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    """Build the same unified analysis shape from manually supplied product data."""
    payload = payload if isinstance(payload, dict) else {}
    nutrient_map = {
        "energy_kcal": "energy_kcal_per_100g",
        "total_fat": "total_fat_per_100g",
        "saturated_fat": "saturated_fat_per_100g",
        "sugar": "sugars_per_100g",
        "fiber": "fiber_per_100g",
        "protein": "protein_per_100g",
        "sodium": "sodium_mg_per_100g",
        "salt": "salt_g_per_100g",
    }
    per_100g = {}
    for key, request_key in nutrient_map.items():
        value = payload.get(request_key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            per_100g[key] = value
    food_label = {
        "product_name": payload.get("product_name"),
        "brand": payload.get("brand"),
        "ingredients": payload.get("ingredients_text"),
        "additives_tags": payload.get("additives") or [],
        "allergen_analysis": {
            "declared": [], "may_contain": [], "ingredient_terms_detected": [],
            "declaration_text": None, "precautionary_text": None,
            "status": "unknown", "review_required": True,
        },
        "warnings": [],
    }
    normalized_nutrition = {
        "per_100g": per_100g,
        "per_serving": {},
        "reference_basis": {"detected": "manual_per_100g"},
        "units": {},
        "warnings": [],
    }
    merged_product = merge_product(
        food_label=food_label,
        normalized_nutrition=normalized_nutrition,
        off_data=None,
    )
    if payload.get("category"):
        merged_product["product"]["categories"] = payload["category"]
        merged_product["data_sources"]["categories"] = "manual_input"

    overrides = {
        "nutri_score": {
            "fruit_vegetable_percent": payload.get("fruit_vegetable_percent"),
            "non_nutritive_sweeteners": payload.get("non_nutritive_sweeteners"),
        },
        "additive_regulatory": {
            "additive_concentrations": payload.get("additive_concentrations") or {},
        },
    }
    food_intelligence = run_food_intelligence(
        merged_product, log=logger or _LOGGER, overrides=overrides
    )
    health_analysis = analyze_health(merged_product, engine_results=food_intelligence)
    scoring = score(scoring_input_from_merged(merged_product))

    missing_fields = []
    if not merged_product["product"].get("name"):
        missing_fields.append("product_name")
    if not merged_product["ingredients"].get("text"):
        missing_fields.append("ingredients")
    if not per_100g:
        missing_fields.append("nutrition_per_100g")
    engine_warnings = [
        result["warning"] for result in food_intelligence.values()
        if isinstance(result, dict) and result.get("status") == "engine_error" and result.get("warning")
    ]
    warnings = list(dict.fromkeys(
        merged_product["warnings"] + health_analysis.get("warnings", []) + engine_warnings
    ))

    return {
        **merged_product,
        "input_source": "manual",
        "nutri_score": food_intelligence["nutri_score"],
        "nova": food_intelligence["nova"],
        "additive_regulatory": food_intelligence["additive_regulatory"],
        "health_analysis": health_analysis,
        "scoring": scoring,
        "warnings": warnings,
        "needs_review": (
            merged_product["needs_review"]
            or health_analysis["needs_review"]
            or bool(missing_fields)
        ),
    }
