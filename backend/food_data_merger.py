"""Merge NutriTrust OCR extraction with Open Food Facts data.

OCR data is treated as evidence from the physical package being scanned. Open Food
Facts enriches missing fields, but its allergen/trace declarations remain separate
because database tags are not the same as label declarations.
"""
from __future__ import annotations

from typing import Any


def _has_value(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def _normalize_off_nutrition(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, dict[str, Any]] = {}
    for nutrient, item in value.items():
        if isinstance(item, dict) and item.get("value") is not None:
            normalized[nutrient] = {
                "value": item["value"],
                "unit": item.get("unit"),
                "basis": item.get("basis", "per_100g"),
                "source": item.get("source", "open_food_facts"),
            }
            for key in ("status", "modifier", "evidence"):
                if item.get(key) is not None:
                    normalized[nutrient][key] = item[key]
    return normalized


def merge_product_data(
    food_label: dict[str, Any],
    normalized_nutrition: dict[str, Any] | None = None,
    off_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge parsed OCR and optional OFF data with field-level provenance.

    OCR ingredients and explicit allergen declarations take precedence when present.
    OFF values fill gaps. Nutrition is merged per reference basis, never mixing
    per-serving and per-100-g numbers into the same map.
    """
    label = food_label if isinstance(food_label, dict) else {}
    norm = normalized_nutrition if isinstance(normalized_nutrition, dict) else {}
    off = off_data if isinstance(off_data, dict) and off_data.get("found") else {}

    def choose(label_value: Any, off_value: Any, label_source: str = "ocr_label") -> tuple[Any, str | None]:
        if _has_value(label_value):
            return label_value, label_source
        if _has_value(off_value):
            return off_value, "open_food_facts"
        return None, None

    ingredients_text, ingredients_source = choose(label.get("ingredients"), off.get("ingredients_text"))
    ingredient_items = label.get("ingredient_items") or []
    ingredient_items_source = "ocr_label" if ingredient_items else None
    if not ingredient_items and isinstance(off.get("ingredients"), list):
        ingredient_items = [
            item.get("text") or item.get("id")
            for item in off["ingredients"]
            if isinstance(item, dict) and (item.get("text") or item.get("id"))
        ]
        if ingredient_items:
            ingredient_items_source = "open_food_facts"

    # Keep the scanned label's allergen analysis separate from database tags/traces.
    allergen_analysis = label.get("allergen_analysis") or {
        "declared": [], "may_contain": [], "ingredient_terms_detected": [],
        "declaration_text": None, "precautionary_text": None,
        "status": "unknown", "review_required": True,
    }

    # Codes printed on the package take precedence; OFF fills the gap otherwise.
    label_additives = label.get("additives_tags") or []
    off_additives = off.get("additives_tags") or []
    if label_additives:
        additives_tags = list(dict.fromkeys(label_additives))
        additives_count = len(additives_tags)
        additives_source = "ocr_label"
    elif _has_value(off_additives) or off.get("additives_count") is not None:
        additives_tags = off_additives
        additives_count = off.get("additives_count")
        additives_source = "open_food_facts"
    else:
        additives_tags = []
        additives_count = None
        additives_source = None

    # Keep per-serving and per-100-g maps separate. OCR wins only when it has values
    # for that same basis; OFF fills gaps. Any disagreements are surfaced for review.
    ocr_per_100g = norm.get("per_100g") if isinstance(norm.get("per_100g"), dict) else {}
    ocr_per_serving = norm.get("per_serving") if isinstance(norm.get("per_serving"), dict) else {}
    off_per_100g = _normalize_off_nutrition(off.get("nutrition_per_100g"))
    off_per_serving = _normalize_off_nutrition(off.get("nutrition_per_serving"))

    per_100g: dict[str, dict[str, Any]] = {}
    nutrition_conflicts: list[dict[str, Any]] = []
    for nutrient in sorted(set(ocr_per_100g) | set(off_per_100g)):
        label_value = ocr_per_100g.get(nutrient)
        off_value = off_per_100g.get(nutrient)
        if label_value is not None:
            unit = "kcal" if nutrient == "energy_kcal" else ("mg" if nutrient in {"sodium", "cholesterol", "calcium", "iron", "potassium"} else "g")
            per_100g[nutrient] = {"value": label_value, "unit": unit, "basis": "per_100g", "source": "ocr_label"}
            if off_value is not None:
                try:
                    differs = abs(float(label_value) - float(off_value["value"])) > max(0.5, abs(float(label_value)) * 0.05)
                except (TypeError, ValueError):
                    differs = label_value != off_value.get("value")
                if differs:
                    nutrition_conflicts.append({
                        "nutrient": nutrient,
                        "ocr_value": label_value,
                        "open_food_facts_value": off_value.get("value"),
                        "unit": unit,
                        "selected_source": "ocr_label",
                        "alternative_source": "open_food_facts",
                        "review_required": True,
                    })
        elif off_value is not None:
            per_100g[nutrient] = off_value

    per_serving: dict[str, dict[str, Any]] = {}
    for nutrient in sorted(set(ocr_per_serving) | set(off_per_serving)):
        label_value = ocr_per_serving.get(nutrient)
        off_value = off_per_serving.get(nutrient)
        if label_value is not None:
            unit = "kcal" if nutrient == "energy_kcal" else ("mg" if nutrient in {"sodium", "cholesterol", "calcium", "iron", "potassium"} else "g")
            per_serving[nutrient] = {"value": label_value, "unit": unit, "basis": "per_serving", "source": "ocr_label"}
        elif off_value is not None:
            per_serving[nutrient] = off_value

    product_name, product_name_source = choose(label.get("product_name"), off.get("product_name"))
    brands, brands_source = choose(label.get("brand"), off.get("brands"))
    barcode, barcode_source = choose(None, off.get("barcode"))
    quantity, quantity_source = choose(None, off.get("quantity"))

    data_sources = {
        "product_name": product_name_source,
        "brands": brands_source,
        "barcode": barcode_source,
        "quantity": quantity_source,
        "categories": "open_food_facts" if _has_value(off.get("categories")) else None,
        "labels_tags": "open_food_facts" if _has_value(off.get("labels_tags")) else None,
        "image_front_url": "open_food_facts" if _has_value(off.get("image_front_url")) else None,
        "image_nutrition_url": "open_food_facts" if _has_value(off.get("image_nutrition_url")) else None,
        "ingredients": ingredients_source,
        "ingredient_items": ingredient_items_source,
        "allergen_analysis": "ocr_label" if _has_value(label.get("allergen_analysis")) else None,
        "allergen_declaration": "ocr_label" if _has_value(allergen_analysis.get("declaration_text")) else None,
        "precautionary_traces": "ocr_label" if _has_value(allergen_analysis.get("precautionary_text")) else None,
        "allergen_database_tags": "open_food_facts" if _has_value(off.get("allergens_tags")) else None,
        "trace_database_tags": "open_food_facts" if _has_value(off.get("traces_tags")) else None,
        "nutrition_per_100g": "merged" if per_100g else None,
        "nutrition_per_serving": "merged" if per_serving else None,
        "nova_group": "open_food_facts" if off.get("nova_group") is not None else None,
        "nutriscore_grade": "open_food_facts" if _has_value(off.get("nutriscore_grade")) else None,
        "environmental_score_grade": "open_food_facts" if _has_value(off.get("environmental_score_grade")) else None,
        "additives": additives_source,
    }

    warnings = list(label.get("warnings") or [])
    if isinstance(off_data, dict) and not off_data.get("found"):
        warnings.append(off_data.get("message") or "Product was not found in Open Food Facts.")
    if off and not off_per_100g:
        warnings.append("Open Food Facts did not provide mapped per-100-g nutrition values.")
    if nutrition_conflicts:
        warnings.append("OCR and Open Food Facts nutrition values differ; scanned-label values were selected and should be reviewed.")

    return {
        "schema_version": "1.0",
        "product": {
            "barcode": barcode,
            "name": product_name,
            "brands": brands,
            "quantity": quantity,
            "categories": off.get("categories"),
            "labels_tags": off.get("labels_tags", []),
            "image_front_url": off.get("image_front_url"),
            "image_nutrition_url": off.get("image_nutrition_url"),
        },
        "ingredients": {
            "text": ingredients_text,
            "items": ingredient_items,
            "source": ingredients_source,
        },
        "allergens": {
            "label_analysis": allergen_analysis,
            "declared": allergen_analysis.get("declared", []),
            "declaration": allergen_analysis.get("declaration_text"),
            "precautionary_traces": {
                "allergens": allergen_analysis.get("may_contain", []),
                "text": allergen_analysis.get("precautionary_text"),
            },
            "open_food_facts_tags": off.get("allergens_tags", []),
            "open_food_facts_declaration": off.get("allergens"),
            "traces_tags": off.get("traces_tags", []),
            "traces_declaration": off.get("traces"),
            "status": "unknown" if not _has_value(allergen_analysis.get("declaration_text")) and not off.get("allergens_tags") else "information_available_review_required",
        },
        "nutrition": {
            "per_100g": per_100g,
            "per_serving": per_serving,
            "ocr_normalization": norm,
            "open_food_facts_basis": off.get("nutrition_basis") if off else None,
            "reference_basis": norm.get("reference_basis", {}).get("detected") if isinstance(norm.get("reference_basis"), dict) else None,
            "source_values": norm.get("source_values", {}),
            "units": norm.get("units", {}),
            "conflicts": nutrition_conflicts,
        },
        "classification": {
            "nova_group": off.get("nova_group"),
            "nutriscore_grade": off.get("nutriscore_grade"),
            "nutriscore": {
                "reported_grade": off.get("nutriscore_grade"),
                "source": "open_food_facts" if _has_value(off.get("nutriscore_grade")) else None,
                "reported_algorithm_version": off.get("nutriscore_version"),
                "calculated_status": "not_calculated",
                "algorithm_version": None,
                "note": "The NutriTrust component score is not an official Nutri-Score calculation.",
            },
            "environmental_score_grade": off.get("environmental_score_grade"),
            "additives_count": additives_count,
            "additives_tags": additives_tags,
        },
        "data_sources": data_sources,
        "open_food_facts": {
            "found": bool(off),
            "nutrition_source": off.get("nutrition_source"),
            "data_quality_errors": off.get("data_quality_errors", []),
            "available_fields": off.get("available_fields", []),
        },
        "warnings": list(dict.fromkeys(warnings)),
        "needs_review": bool(warnings) or bool(nutrition_conflicts) or bool(allergen_analysis.get("review_required", True)),
    }
