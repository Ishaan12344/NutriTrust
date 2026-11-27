"""Normalize parsed food-label nutrition into a consistent per-serving/per-100 g schema.

This module performs unit conversion and arithmetic only. It does not estimate missing
nutrients or silently assume a label's reference basis when it cannot be identified.
"""

from __future__ import annotations

import re
import math
from typing import Any

# Parser field -> API/scoring field and expected canonical unit.
NUTRIENT_SCHEMA: dict[str, tuple[str, str]] = {
    "monounsaturated_fat": ("monounsaturated_fat", "g"),
    "polyunsaturated_fat": ("polyunsaturated_fat", "g"),
    "total_fat": ("total_fat", "g"),
    "saturated_fat": ("saturated_fat", "g"),
    "trans_fat": ("trans_fat", "g"),
    "cholesterol": ("cholesterol", "mg"),
    "sodium": ("sodium", "mg"),
    "total_carbohydrate": ("total_carbohydrate", "g"),
    "dietary_fiber": ("fiber", "g"),
    "total_sugars": ("sugar", "g"),
    "added_sugars": ("added_sugar", "g"),
    "protein": ("protein", "g"),
    "calcium": ("calcium", "mg"),
    "iron": ("iron", "mg"),
    "potassium": ("potassium", "mg"),
}


def _positive_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _detect_basis(raw_text: str, parsed: dict[str, Any] | None = None) -> str:
    """Return per_100g, per_serving, or unknown based on explicit basis.

    A table-parser-supplied ``reference_basis`` wins over scanning raw text,
    which can contain both `per serving` and `per 100 g` headers in one table.
    """
    explicit = (parsed or {}).get("reference_basis")
    if isinstance(explicit, dict):
        detected = explicit.get("detected")
    else:
        detected = explicit
    if detected in {"per_100g", "per_serving"}:
        return detected

    text = (raw_text or "").lower().replace("100grams", "100 grams")
    has_100g = bool(
        re.search(r"(?:\bper\s*|/\s*)100\s*(?:gms?|g|ml|grams?)\b|\b100\s*(?:gms?|g)\s*(?:basis|values?)\b", text)
    )
    has_serving = bool(
        re.search(
            r"\bper\s+serving\b|\bamount\s+per\s+serving\b|\bper\s+portion\b", text
        )
    )
    if has_100g and has_serving:
        return "ambiguous"
    if has_100g:
        return "per_100g"
    if has_serving:
        return "per_serving"
    return "unknown"


def _convert_unit(value: float, source_unit: str, target_unit: str) -> float | None:
    unit = (source_unit or "").strip().lower().replace("μ", "µ")
    unit = {
        "ug": "mcg",
        "µg": "mcg",
        "microgram": "mcg",
        "micrograms": "mcg",
        "gram": "g",
        "grams": "g",
        "gm": "g",
        "gms": "g",
        "milligram": "mg",
        "milligrams": "mg",
    }.get(unit, unit)
    if target_unit == "g":
        factors = {"g": 1.0, "mg": 0.001, "mcg": 0.000001}
    elif target_unit == "mg":
        factors = {"g": 1000.0, "mg": 1.0, "mcg": 0.001}
    elif target_unit == "kcal":
        factors = {"kcal": 1.0, "cal": 1.0, "calorie": 1.0, "calories": 1.0}
    else:
        return None
    factor = factors.get(unit)
    return value * factor if factor is not None else None


def _round_values(values: dict[str, float]) -> dict[str, float]:
    return {key: round(value, 4) for key, value in values.items()}


def normalize_nutrition(parsed: dict[str, Any], basis: str = "auto") -> dict[str, Any]:
    """Return normalized nutrition per serving and per 100 g.

    Args:
        parsed: Output from ``parse_food_label``.
        basis: ``auto``, ``per_serving``, or ``per_100g``. Use an explicit value only
            when verified from the package. ``auto`` trusts only clear wording in OCR.

    Unknown source basis or missing serving weight is retained as unknown rather than
    filled with zeros. Values in the returned maps are canonicalized to g, mg, or kcal.
    """
    if basis not in {"auto", "per_serving", "per_100g"}:
        raise ValueError("basis must be 'auto', 'per_serving', or 'per_100g'")

    raw_text = str(parsed.get("raw_text") or "")
    detected_basis = _detect_basis(raw_text, parsed) if basis == "auto" else basis
    serving = parsed.get("serving_size") or {}
    serving_g = (
        _positive_number(serving.get("weight_g")) if isinstance(serving, dict) else None
    )

    source_values: dict[str, float] = {}
    source_units: dict[str, str] = {}
    nutrition = parsed.get("nutrition") or {}
    if not isinstance(nutrition, dict):
        nutrition = {}

    for parser_key, (api_key, target_unit) in NUTRIENT_SCHEMA.items():
        item = nutrition.get(parser_key)
        if not isinstance(item, dict):
            continue

        raw_value = item.get("value")
        if raw_value is None or isinstance(raw_value, bool):
            continue

        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        if value < 0:
            continue
        converted = _convert_unit(value, str(item.get("unit", "")), target_unit)
        if converted is None:
            continue
        source_values[api_key] = converted
        source_units[api_key] = target_unit

    # Energy is parsed separately by the label parser. The displayed value follows the
    # nutrition panel's basis, so it is handled just like the other panel quantities.
    energy = parsed.get("calories_per_serving_kcal")
    try:
        energy = float(energy) if energy is not None else None
    except (TypeError, ValueError):
        energy = None
    if energy is not None and energy >= 0:
        source_values["energy_kcal"] = energy
        source_units["energy_kcal"] = "kcal"

    per_serving: dict[str, float] = {}
    per_100g: dict[str, float] = {}
    warnings: list[str] = []
    nutrition_review = parsed.get("nutrition_review")
    if not isinstance(nutrition_review, list):
        nutrition_review = []
    if nutrition_review:
        warnings.append(
            "Some OCR nutrition rows are invalid, suspicious, or unresolved and were excluded from normalization."
        )

    if detected_basis == "per_serving":
        per_serving = dict(source_values)
        if serving_g:
            per_100g = {
                key: value * 100.0 / serving_g for key, value in source_values.items()
            }
        elif source_values:
            warnings.append(
                "Serving weight is missing or invalid; per-100-g values cannot be calculated."
            )
    elif detected_basis == "per_100g":
        per_100g = dict(source_values)
        if serving_g:
            per_serving = {
                key: value * serving_g / 100.0 for key, value in source_values.items()
            }
        elif source_values:
            warnings.append(
                "Serving weight is missing or invalid; per-serving values cannot be calculated."
            )
    elif detected_basis == "ambiguous":
        warnings.append(
            "OCR mentions both per-100-g and per-serving bases; values were not converted because their column basis is ambiguous."
        )
    elif source_values:
        warnings.append(
            "Nutrition reference basis was not explicit in OCR; values are preserved as source values and not converted."
        )

    servings_per_container = _positive_number(parsed.get("servings_per_container"))
    whole_package: dict[str, float] = {}
    if servings_per_container and per_serving:
        whole_package = {
            key: value * servings_per_container for key, value in per_serving.items()
        }
    elif per_serving:
        warnings.append(
            "Whole-package nutrition was not calculated because servings per container is missing or invalid."
        )
    elif parsed.get("servings_per_container") and not per_serving:
        warnings.append(
            "Whole-package nutrition was not calculated because per-serving values are unavailable."
        )

    # Round only at the output boundary; calculations above use full precision.
    return {
        "schema_version": "1.0",
        "serving_size": {
            "text": serving.get("text") if isinstance(serving, dict) else None,
            "weight_g": serving_g,
        },
        "servings_per_container": (
            int(servings_per_container)
            if servings_per_container and servings_per_container.is_integer()
            else servings_per_container
        ),
        "reference_basis": {
            "requested": basis,
            "detected": detected_basis,
            "status": (
                "known"
                if detected_basis in {"per_serving", "per_100g"}
                else "unknown_or_ambiguous"
            ),
        },
        "units": {
            "energy_kcal": "kcal",
            "fat": "g",
            "carbohydrate": "g",
            "protein": "g",
            "fiber": "g",
            "sugar": "g",
            "sodium": "mg",
            "cholesterol": "mg",
            "minerals": "mg",
        },
        "source_values": _round_values(source_values),
        "per_serving": _round_values(per_serving),
        "per_100g": _round_values(per_100g),
        "whole_package": _round_values(whole_package),
        "daily_values_percent": parsed.get("daily_values_percent") or {},
        "nutrition_review": nutrition_review,
        "warnings": warnings,
        "needs_review": bool(warnings)
        or bool((parsed.get("extraction") or {}).get("needs_review")),
    }
