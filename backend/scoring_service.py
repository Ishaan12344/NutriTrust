"""
Scoring Service
NutriTrust hybrid scoring engine combining:
  1. Nutri-Score (nutrient quality) Ã¢â‚¬â€ 40%
  2. NOVA classification (processing level) Ã¢â‚¬â€ 25%
  3. UK Traffic Light (nutrient limits) Ã¢â‚¬â€ 20%
  4. Additive safety analysis Ã¢â‚¬â€ 15%
"""

import json
import math
import os
import re
from scoring_config import (
    CUSTOM_NUTRIENT_QUALITY_VERSION,
    NOVA_TO_CUSTOM_SCORE,
    SCORING_FORMULA_VERSION,
    SCORING_WEIGHTS,
    GRADE_THRESHOLDS,
    TRAFFIC_LIGHT_THRESHOLDS,
    TRAFFIC_LIGHT_SCORES,
    CUSTOM_NUTRIENT_NEGATIVE,
    CUSTOM_NUTRIENT_POSITIVE,
    WHO_DAILY_LIMITS,
)

# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
# Load data files
# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

with open(os.path.join(_DATA_DIR, "additives.json"), "r", encoding="utf-8") as f:
    ADDITIVES_DB = json.load(f)

with open(os.path.join(_DATA_DIR, "nova_markers.json"), "r", encoding="utf-8") as f:
    NOVA_MARKERS = json.load(f)


def _numeric_nutrition(raw: dict) -> dict:
    """Convert NutriTrust nutrient objects to the engine's numeric schema."""
    result = {}
    for name, item in (raw or {}).items():
        value = item.get("value") if isinstance(item, dict) else item
        if isinstance(item, dict):
            basis = item.get("basis")
            if basis is not None and basis != "per_100g":
                continue
            unit = str(item.get("unit") or "").strip().casefold()
            if unit:
                if name == "energy_kcal":
                    if unit in {"kj", "kilojoule", "kilojoules"}:
                        try:
                            value = float(value) / 4.184
                        except (TypeError, ValueError):
                            continue
                    elif unit not in {"kcal", "kilocalorie", "kilocalories"}:
                        continue
                elif name == "sodium":
                    if unit == "g":
                        try:
                            value = float(value) * 1000
                        except (TypeError, ValueError):
                            continue
                    elif unit not in {"mg", "milligram", "milligrams"}:
                        continue
                elif name == "salt":
                    if unit == "mg":
                        try:
                            value = float(value) / 1000
                        except (TypeError, ValueError):
                            continue
                    elif unit != "g":
                        continue
                elif name in {"total_fat", "saturated_fat", "trans_fat", "total_carbohydrate", "fiber", "sugar", "added_sugar", "protein"}:
                    if unit == "mg":
                        try:
                            value = float(value) / 1000
                        except (TypeError, ValueError):
                            continue
                    elif unit != "g":
                        continue
        if isinstance(value, bool):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number) and number >= 0:
            result[name] = number
    if "sodium" not in result and "salt" in result:
        result["sodium"] = result["salt"] * 1000 / 2.5
    return result


def _missing_required_nutrients(nutrition: dict) -> list[str]:
    required = {
        "energy_kcal": "energy",
        "saturated_fat": "saturated fat",
        "sugar": "sugar",
        "sodium": "sodium",
        "fiber": "fiber",
        "protein": "protein",
    }
    return [label for key, label in required.items() if key not in nutrition]


def rate(product_data: dict) -> dict:
    """Compute the existing NutriTrust hybrid rating from normalized product data."""
    nutrition = _numeric_nutrition(product_data.get("nutrition_per_100g", {}))
    ingredients_text = product_data.get("ingredients_text") or ""
    additives_tags = product_data.get("additives_tags") or []
    additives_available = product_data.get("additives_available")
    if additives_available is None:
        additives_available = bool(additives_tags) or bool(
            re.search(r"\bE\s*\d{3,4}[A-Z]?\b", ingredients_text, re.IGNORECASE)
        )
    known_nova = product_data.get("nova_group")
    nova_source = product_data.get("nova_source")

    nutrient_result = _compute_nutrient_quality(nutrition)
    nova_result = _compute_nova_score(ingredients_text, known_nova, nova_source)
    product = product_data.get("product") if isinstance(product_data.get("product"), dict) else {}
    category_text = str(product.get("categories") or "").casefold()
    is_beverage = bool(re.search(r"\b(beverage|beverages|drink|drinks)\b", category_text))
    limits_result = _compute_nutrient_limits(nutrition, beverage=is_beverage)
    additive_result = _compute_additive_score(
        additives_tags, ingredients_text, additives_available, product_data.get("additives_count")
    )

    missing_data = _missing_required_nutrients(nutrition)
    if not ingredients_text:
        missing_data.append("ingredients")
    if not additives_available:
        missing_data.append("additive information")
    elif additive_result["score"] is None:
        missing_data.append("complete additive assessment")
    missing_data.extend(nutrient_result["missing_data"])
    if limits_result["score"] is None:
        missing_data.append("nutrient limits")
    if nova_result["score"] is None:
        missing_data.append("verified NOVA classification")
    conflicts = product_data.get("nutrition_conflicts") or []
    scored_nutrients = {"energy_kcal", "saturated_fat", "sugar", "sodium"}
    material_conflicts = [
        conflict for conflict in conflicts
        if isinstance(conflict, dict) and conflict.get("nutrient") in scored_nutrients
    ]
    if material_conflicts:
        missing_data.append("unresolved conflicts in scored nutrients")
    missing_data = list(dict.fromkeys(missing_data))
    displayed_nutrients = {
        "energy_kcal", "total_fat", "saturated_fat", "trans_fat",
        "total_carbohydrate", "fiber", "sugar", "added_sugar", "protein",
        "sodium", "salt", "cholesterol", "calcium", "iron", "potassium",
    }
    per_serving_raw = product_data.get("nutrition_per_serving")
    serving_nutrients = _numeric_nutrition(per_serving_raw) if isinstance(per_serving_raw, dict) else {}
    nutrition_missing = sorted(displayed_nutrients - (set(nutrition) | set(serving_nutrients)))
    if not product_data.get("serving_size_available", False):
        nutrition_missing.append("serving_size")
    nutrition_missing = sorted(set(nutrition_missing))

    component_scores = {
        "nutrient_quality": nutrient_result["score"],
        "nova_processing": nova_result["score"],
        "nutrient_limits": limits_result["score"],
        "additive_safety": additive_result["score"],
    }
    available_components = {
        name: score for name, score in component_scores.items()
        if isinstance(score, (int, float)) and not isinstance(score, bool)
    }
    available_weight = sum(SCORING_WEIGHTS[name] for name in available_components)
    unavailable_components = [
        name for name in component_scores if name not in available_components
    ]
    effective_weights = {
        name: (
            round(SCORING_WEIGHTS[name] / available_weight, 6)
            if name in available_components and available_weight
            else None
        )
        for name in SCORING_WEIGHTS
    }

    if not available_components:
        overall_score = None
        grade = "N/A"
        grade_label = "No Scorable Data"
        score_status = "not_calculated"
        explanation = (
            "A NutriTrust score was not calculated because no component had valid inputs: "
            + ", ".join(missing_data)
            + "."
        )
    else:
        score_status = "provisional" if not unavailable_components and not missing_data else "partial"
        overall_score = round(
            sum(effective_weights[name] * score for name, score in available_components.items())
        )
        overall_score = max(0, min(100, overall_score))
        grade, grade_label = _get_grade(overall_score)
        explanation = _generate_explanation(
            overall_score, grade, nutrition, nutrient_result, nova_result,
            limits_result, additive_result
        )
        if unavailable_components:
            explanation += (
                " This provisional score uses the available components with their "
                "configured weights normalized to 100%; unavailable components: "
                + ", ".join(unavailable_components)
                + "."
            )
    rating_reasons = _rating_reasons(
        nutrition, nova_result, limits_result, additive_result, limit=2
    )
    contributions = {
        name: None if value is None else round(effective_weights[name] * value, 2)
        for name, value in component_scores.items()
    }
    return {
        "formula_version": SCORING_FORMULA_VERSION,
        "weights": dict(SCORING_WEIGHTS),
        "effective_weights": effective_weights,
        "component_scores": component_scores,
        "contributions": contributions,
        "score_status": score_status,
        "product": product_data.get("product", {}),
        "nutrition_per_100g": nutrition,
        "ingredients_text": ingredients_text,
        "additives_tags": additives_tags,
        "nova_group": known_nova if known_nova is not None else nova_result["nova_group"],
        "data_sufficiency": {
            "status": "partial" if nutrition_missing else "available",
            "missing": missing_data,
            "nutrition": {"status": "partial" if nutrition_missing else "available", "missing_fields": nutrition_missing},
            "ingredients": "provided_unverified" if ingredients_text else "missing",
            "scoring_eligibility": (
                "eligible_provisional" if score_status == "provisional"
                else "eligible_partial" if score_status == "partial"
                else "ineligible"
            ),
            "unavailable_components": unavailable_components,
            "score_confidence": "not_calibrated",
        },
        "scores": {
            "overall": overall_score,
            "grade": grade,
            "grade_label": grade_label,
            "nutrient_quality": {
                "score": nutrient_result["score"],
                "ruleset": CUSTOM_NUTRIENT_QUALITY_VERSION,
                "negative_points": nutrient_result["negative_points"],
                "positive_points": nutrient_result["positive_points"],
                "details": nutrient_result["details"],
                "missing_data": nutrient_result["missing_data"],
            },
            "nova_processing": {
                "score": nova_result["score"],
                "nova_group": nova_result["nova_group"],
                "source": nova_result["source"],
                "markers_found": nova_result["markers_found"],
                "details": nova_result["details"],
            },
            "nutrient_limits": {
                "score": limits_result["score"],
                "traffic_lights": limits_result["traffic_lights"],
                "energy_reference": limits_result["energy_reference"],
                "ruleset": limits_result["ruleset"],
                "details": limits_result["details"],
            },
            "additive_safety": {
                "score": additive_result["score"],
                "status": additive_result["status"],
                "flagged_additives": additive_result["flagged_additives"],
                "total_additives": additive_result["total_additives"],
                "unverified_additives": additive_result.get("unverified_additives", []),
                "details": additive_result["details"],
            },
        },
        "explanation": explanation,
        # A compact, display-ready explanation for the rating.  The full
        # explanation remains available to summaries, while the client can
        # present these one or two concrete reasons directly below the score.
        "rating_reasons": rating_reasons,
    }

# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
# 1. Custom nutrient-quality component (not an official Nutri-Score)
#    Weight: 40%
# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

def _compute_nutrient_quality(nutrition: dict) -> dict:
    """Compute nutrient quality without turning missing values into zero."""
    required = ("energy_kcal", "sugar", "saturated_fat", "sodium")
    missing = [key for key in required if key not in nutrition]
    if missing:
        return {
            "score": None,
            "negative_points": None,
            "positive_points": None,
            "raw_score": None,
            "missing_data": missing,
            "details": "Missing required nutrients: " + ", ".join(missing),
        }

    energy_kcal = nutrition["energy_kcal"]
    sugar = nutrition["sugar"]
    sat_fat = nutrition["saturated_fat"]
    sodium = nutrition["sodium"]
    energy_kj = energy_kcal * 4.184
    neg_energy = _score_from_thresholds(energy_kj, CUSTOM_NUTRIENT_NEGATIVE["energy_kj"])
    neg_sugar = _score_from_thresholds(sugar, CUSTOM_NUTRIENT_NEGATIVE["sugar"])
    neg_sat_fat = _score_from_thresholds(sat_fat, CUSTOM_NUTRIENT_NEGATIVE["saturated_fat"])
    neg_sodium = _score_from_thresholds(sodium, CUSTOM_NUTRIENT_NEGATIVE["sodium"])
    negative_total = neg_energy + neg_sugar + neg_sat_fat + neg_sodium

    positive_total = 0
    details_parts = []
    if "fiber" in nutrition:
        pos_fiber = _score_from_thresholds(nutrition["fiber"], CUSTOM_NUTRIENT_POSITIVE["fiber"])
        positive_total += pos_fiber
        if pos_fiber >= 3:
            details_parts.append(f"Good fiber content ({nutrition['fiber']}g/100g)")
    if "protein" in nutrition:
        pos_protein = _score_from_thresholds(nutrition["protein"], CUSTOM_NUTRIENT_POSITIVE["protein"])
        positive_total += pos_protein
        if pos_protein >= 3:
            details_parts.append(f"Good protein content ({nutrition['protein']}g/100g)")
    if neg_sugar >= 5:
        details_parts.append(f"High sugar ({sugar}g/100g)")
    if neg_sat_fat >= 5:
        details_parts.append(f"High saturated fat ({sat_fat}g/100g)")
    if neg_sodium >= 5:
        details_parts.append(f"High sodium ({sodium}mg/100g)")
    if neg_energy >= 5:
        details_parts.append(f"High energy density ({energy_kcal} kcal/100g)")
    if not details_parts:
        details_parts.append("Moderate nutrient profile")

    raw_score = negative_total - positive_total
    score = round(max(0, min(100, 100 - (raw_score + 10) * 2)))
    return {
        "score": score,
        "negative_points": negative_total,
        "positive_points": positive_total,
        "raw_score": raw_score,
        "missing_data": [],
        "details": "; ".join(details_parts),
    }

def _score_from_thresholds(value: float, thresholds: list) -> int:
    """Score a value against ascending threshold list. Returns 0 to len(thresholds)."""
    for i, threshold in enumerate(thresholds):
        if value <= threshold:
            return i
    return len(thresholds)


# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
# 2. NOVA Processing Score
#    Weight: 25%
# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

def _compute_nova_score(ingredients_text: str, known_nova, nova_source=None) -> dict:
    """Use a sourced NOVA classification; ingredient marker counts are insufficient."""
    ingredients_lower = ingredients_text.lower() if ingredients_text else ""
    found_markers = [
        marker for marker in NOVA_MARKERS.get("nova4_markers", [])
        if marker in ingredients_lower
    ]
    trusted = (
        isinstance(known_nova, (int, float))
        and not isinstance(known_nova, bool)
        and float(known_nova).is_integer()
        and 1 <= int(known_nova) <= 4
        and nova_source in {"open_food_facts", "nutritrust_nova_engine"}
    )
    if trusted:
        nova_group = int(known_nova)
        source = nova_source
        score = NOVA_TO_CUSTOM_SCORE[nova_group]
    else:
        nova_group = None
        source = "unavailable"
        score = None
    nova_labels = {
        1: "Unprocessed or minimally processed",
        2: "Processed culinary ingredient",
        3: "Processed food",
        4: "Ultra-processed food product",
    }
    details = (
        f"NOVA Group {nova_group}: {nova_labels[nova_group]}"
        if nova_group is not None
        else "A sourced NOVA classification is unavailable; ingredient markers alone do not establish a NOVA group."
    )
    if found_markers:
        details += f". Markers found: {', '.join(found_markers[:5])}"
    return {
        "score": score,
        "nova_group": nova_group,
        "source": source,
        "markers_found": found_markers,
        "details": details,
    }

def _compute_nutrient_limits(nutrition: dict, *, beverage: bool = False) -> dict:
    """Compute traffic lights only for measured nutrients."""
    if beverage:
        empty_lights = {
            name: {"color": "gray", "value": None, "unit": "", "verified": False}
            for name in ("total_fat", "saturated_fat", "sugar", "salt")
        }
        return {
            "score": None,
            "traffic_lights": empty_lights,
            "energy_reference": {"value": None, "unit": "kJ", "basis": "per_100ml", "color_status": "not_colored_by_uk_fop_scheme"},
            "ruleset": {"id": "uk_fop_traffic_lights", "version": "2016-guidance", "category": "beverage", "basis": "per_100ml"},
            "details": "Beverage traffic lights require per-100-ml values. Available per-100-g values were not used.",
        }
    traffic_lights = {}
    total_score = 0
    valid_count = 0
    sodium = nutrition.get("sodium")
    salt = nutrition.get("salt")
    if salt is None and sodium is not None:
        # Sodium is canonicalized to mg/100 g; UK traffic lights use salt g/100 g.
        salt = sodium * 2.5 / 1000
    nutrient_map = {
        "total_fat": nutrition.get("total_fat"),
        "sugar": nutrition.get("sugar"),
        "salt": salt,
        "saturated_fat": nutrition.get("saturated_fat"),
    }
    for nutrient, value in nutrient_map.items():
        if value is None:
            traffic_lights[nutrient] = {"color": "gray", "value": None, "unit": "", "verified": False}
            continue
        thresholds = TRAFFIC_LIGHT_THRESHOLDS[nutrient]
        if value <= thresholds["green"]:
            color = "green"
        elif value <= thresholds["amber"]:
            color = "amber"
        else:
            color = "red"
        traffic_lights[nutrient] = {
            "color": color,
            "value": value,
            "unit": thresholds.get("unit", ""),
            "thresholds": {"green": thresholds["green"], "amber": thresholds["amber"]},
            "verified": True,
        }
        total_score += TRAFFIC_LIGHT_SCORES[color]
        valid_count += 1
    return {
        "score": round((total_score / (valid_count * 25)) * 100) if valid_count else None,
        "traffic_lights": traffic_lights,
        "energy_reference": {
            "value": nutrition.get("energy_kcal") * 4.184 if nutrition.get("energy_kcal") is not None else None,
            "unit": "kJ",
            "basis": "per_100g",
            "color_status": "not_colored_by_uk_fop_scheme",
        },
        "ruleset": {"id": "uk_fop_traffic_lights", "version": "2016-guidance", "category": "solid_food", "basis": "per_100g"},
        "details": "UK front-of-pack colors apply to sugars, saturated fat and salt. Energy is reported without a traffic-light color; sodium is converted to salt using sodium x 2.5.",
    }

def _format_nutrient_name(name: str) -> str:
    """Format nutrient key to display name."""
    return name.replace("_", " ").replace("energy kcal", "calories").title()


# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
# 4. Additive Safety Score
#    Weight: 15%
# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

def _compute_additive_score(additives_tags: list, ingredients_text: str, additives_available: bool, additives_count=None) -> dict:
    """Score known additives and distinguish unavailable data from no findings."""
    if not additives_available:
        return {
            "score": None,
            "status": "unavailable",
            "flagged_additives": [],
            "total_additives": 0,
            "details": "Additive information was not available; absence was not inferred.",
        }

    flagged = []
    penalty = 0
    matched_additives = []
    normalized_tags = []
    for tag in additives_tags:
        code = re.sub(r"^en:", "", str(tag).strip(), flags=re.IGNORECASE).replace("-", "").upper()
        if code:
            normalized_tags.append(code)
    for match in re.finditer(r"\bE\s*(\d{3,4}[A-Z]?)\b", ingredients_text or "", re.IGNORECASE):
        normalized_tags.append("E" + re.sub(r"\s+", "", match.group(1)).upper())

    unknown = []
    for tag_clean in normalized_tags:
        if tag_clean in matched_additives:
            continue
        if tag_clean not in ADDITIVES_DB:
            unknown.append(tag_clean)
            continue
        matched_additives.append(tag_clean)
        entry = ADDITIVES_DB[tag_clean]
        if entry["risk"] == "caution":
            penalty += 5
            flagged.append(f"{tag_clean} - {entry['name']} (Caution: {entry['reason']})")
        elif entry["risk"] == "avoid":
            penalty += 15
            flagged.append(f"{tag_clean} - {entry['name']} (Avoid: {entry['reason']})")

    if unknown:
        return {
            "score": None,
            "status": "unverified_matches",
            "flagged_additives": flagged,
            "total_additives": len(matched_additives) + len(set(unknown)),
            "unverified_additives": sorted(set(unknown)),
            "details": "Some identified additive codes have no entry in the local reference data; assessment is incomplete.",
        }
    try:
        expected_count = int(additives_count) if additives_count is not None else None
    except (TypeError, ValueError):
        expected_count = None
    if expected_count is None:
        return {
            "score": None,
            "status": "incomplete_inventory",
            "flagged_additives": flagged,
            "total_additives": len(matched_additives),
            "unverified_additives": [],
            "details": "The source did not provide a total additive count, so the identified set cannot be checked for completeness.",
        }
    if expected_count != len(matched_additives):
        return {
            "score": None,
            "status": "incomplete_matches",
            "flagged_additives": flagged,
            "total_additives": len(matched_additives),
            "unverified_additives": [],
            "details": f"The source reports {expected_count} additives, but {len(matched_additives)} distinct codes were identified and matched.",
        }
    score = max(0, 100 - penalty)
    safe_count = len(matched_additives) - len(flagged)
    details = (
        f"{len(matched_additives)} additive(s) detected: {len(flagged)} flagged, {safe_count} with no configured concern; this is not a universal safety guarantee"
        if matched_additives else "No additives were identified in the available additive data."
    )
    return {
        "score": score,
        "status": "known",
        "unverified_additives": [],
        "flagged_additives": flagged,
        "total_additives": len(matched_additives),
        "details": details,
    }

def _get_grade(score: int) -> tuple:
    """Map overall score to letter grade and label."""
    for threshold, grade, label in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade, label
    return "F", "Avoid Ã¢â‚¬â€ extremely unhealthy"


# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
# Explanation Generator
# Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬

def _rating_reasons(
    nutrition: dict,
    nova_result: dict,
    limits_result: dict,
    additive_result: dict,
    *,
    limit: int = 2,
) -> list[str]:
    """Return the most useful one or two plain-language score drivers."""
    concerns: list[str] = []
    positives: list[str] = []
    traffic_lights = limits_result.get("traffic_lights", {})
    if isinstance(traffic_lights, dict):
        for nutrient, label in (
            ("sugar", "Sugar"),
            ("salt", "Salt"),
            ("saturated_fat", "Saturated fat"),
        ):
            value = traffic_lights.get(nutrient)
            if isinstance(value, dict) and value.get("color") == "red":
                concerns.append(f"{label} is high per 100 g.")
    if nova_result.get("nova_group") == 4:
        concerns.append("This is classified as ultra-processed (NOVA 4).")
    if additive_result.get("flagged_additives"):
        concerns.append(
            f"{len(additive_result['flagged_additives'])} additive(s) need caution."
        )
    if nova_result.get("nova_group") == 1:
        positives.append("It is minimally processed (NOVA 1).")
    if nutrition.get("fiber", 0) >= 3:
        positives.append(f"It provides {nutrition['fiber']:g} g fiber per 100 g.")
    if nutrition.get("protein", 0) >= 8:
        positives.append(f"It provides {nutrition['protein']:g} g protein per 100 g.")
    return (concerns + positives)[:limit] or [
        "Based on the available nutrition and ingredient information."
    ]


def _generate_explanation(
    overall_score: int,
    grade: str,
    nutrition: dict,
    nutrient_result: dict,
    nova_result: dict,
    limits_result: dict,
    additive_result: dict,
) -> str:
    """Generate a human-readable summary explanation."""
    parts = [f"This product scores {overall_score}/100 (Grade {grade})."]

    # Main concerns
    concerns = []
    positives = []

    # Sodium concern
    sodium = nutrition.get("sodium") or 0
    if sodium > 0:
        daily_pct = round((sodium / WHO_DAILY_LIMITS["sodium"]) * 100)
        if daily_pct > 30:
            concerns.append(f"very high sodium at {daily_pct}% of daily limit per 100g")
        elif daily_pct > 15:
            concerns.append(f"moderate sodium at {daily_pct}% of daily limit per 100g")

    # Sugar concern
    sugar = nutrition.get("sugar") or 0
    if sugar > 0:
        daily_pct = round((sugar / WHO_DAILY_LIMITS["sugar"]) * 100)
        if daily_pct > 30:
            concerns.append(f"high sugar at {daily_pct}% of daily limit per 100g")

    # Processing concern
    if nova_result["nova_group"] == 4:
        markers = nova_result["markers_found"][:3]
        if markers:
            concerns.append(
                f"ultra-processed (NOVA 4) with markers: {', '.join(markers)}"
            )
        else:
            concerns.append("classified as ultra-processed (NOVA 4)")
    elif nova_result["nova_group"] == 1:
        positives.append("minimally processed (NOVA 1)")

    # Additive concern
    if additive_result["flagged_additives"]:
        count = len(additive_result["flagged_additives"])
        concerns.append(f"{count} additive(s) flagged for caution/avoidance")

    # Good nutrients
    fiber = nutrition.get("fiber") or 0
    protein = nutrition.get("protein") or 0
    if fiber >= 3:
        positives.append(f"good fiber ({fiber}g/100g)")
    if protein >= 8:
        positives.append(f"good protein ({protein}g/100g)")


    if concerns:
        parts.append("Concerns: " + "; ".join(concerns) + ".")
    if positives:
        parts.append("Positives: " + "; ".join(positives) + ".")

    return " ".join(parts)




