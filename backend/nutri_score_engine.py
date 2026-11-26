"""Deterministic implementation of the updated (2023) Nutri-Score algorithm.

The engine deliberately knows nothing about HTTP, databases, or OCR. It consumes
a flat product dictionary and returns an explainable result. Authoritative
sources and implementation limitations are recorded in
``FOOD_INTELLIGENCE_REFERENCES.md``.
"""

from __future__ import annotations

import math
import re
from bisect import bisect_left, bisect_right
from typing import Any

ALGORITHM_VERSION = "updated_2023"
REFERENCE_BASIS = "per_100g_solid_or_per_100ml_liquid_as_declared"

# Each list holds the upper bound for point 0, 1, 2, ... A value equal to a
# bound stays in the lower point band, so bisect_right gives the point index.
ENERGY_GENERAL = [335, 670, 1005, 1340, 1675, 2010, 2345, 2680, 3015, 3350]
SUGARS_GENERAL = [3.4, 6.8, 10, 14, 17, 20, 24, 27, 31, 34, 37, 41, 44, 48, 51]
SFA_GENERAL = list(range(1, 11))
SALT_GENERAL = [round(0.2 * step, 1) for step in range(1, 21)]

ENERGY_BEVERAGE = [30, 90, 150, 210, 240, 270, 300, 330, 360, 390]
SUGARS_BEVERAGE = [0.5, 2, 3.5, 5, 6, 7, 8, 9, 10, 11]
SFA_BEVERAGE = list(range(1, 11))

ENERGY_FAT_SFA = [120 * step for step in range(1, 11)]
SFA_RATIO_FAT = [10, 16, 22, 28, 34, 40, 46, 52, 58, 64]

PROTEIN_GENERAL = [2.4, 4.8, 7.2, 9.6, 12, 14, 17]
FIBRE_GENERAL = [3.0, 4.1, 5.2, 6.3, 7.4]
FVL_GENERAL = [40, 60, 80]
FVL_POINTS_GENERAL = [0, 1, 2, 5]

PROTEIN_BEVERAGE = [1.2, 1.5, 1.8, 2.1, 2.4, 2.7, 3.0]
FIBRE_BEVERAGE = [3.0, 4.1, 5.2, 6.3, 7.4]
FVL_BEVERAGE = [40, 60, 80]
FVL_POINTS_BEVERAGE = [0, 2, 4, 6]

NNS_TERMS = (
    "aspartame", "acesulfame", "sucralose", "saccharin", "cyclamate",
    "neotame", "advantame", "steviol", "thaumatin",
)
NNS_CODES = {"E950", "E951", "E954", "E955", "E957", "E959", "E960", "E961"}

MANDATORY_INPUTS = ("energy_kj", "sugars", "saturated_fat", "salt")

CATEGORY_LABELS = {
    "general_food": "General food",
    "beverage": "Beverage",
    "beverage_water": "Mineral/table/spring water",
    "cheese": "Cheese",
    "red_meat": "Red meat",
    "fats_oils_nuts_seeds": "Fats, oils, nuts or seeds",
}

CAPS = {
    "energy_kj": 4000.0,
    "sugars": 100.0,
    "saturated_fat": 100.0,
    "total_fat": 100.0,
    "sodium_mg": 100000.0,
    "salt": 40.0,
    "fibre": 100.0,
    "protein": 100.0,
    "fruit_vegetable_percent": 100.0,
}


def _points(value: float, thresholds: list[float]) -> int:
    """Return the official point band for a non-negative value.

    Each threshold is the inclusive upper bound of the preceding point band,
    so a value equal to a threshold stays in the lower band.
    """
    return bisect_left(thresholds, value)


def _coerce(value: Any) -> tuple[float | None, str | None]:
    if value is None or isinstance(value, bool):
        return None, None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, f"Non-numeric value {value!r} was ignored."
    if not math.isfinite(number):
        return None, f"Non-finite value {value!r} was ignored."
    if number < 0:
        return None, f"Negative value {value!r} is not a valid nutrient amount."
    return number, None


def _first(data: dict[str, Any], *keys: str) -> tuple[Any, str | None]:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key], key
    return None, None


def detect_category(data: dict[str, Any]) -> dict[str, Any]:
    """Identify the Nutri-Score category from declared category or product name.

    Category inference from a free-text name is an implementation heuristic; it
    is reported so that callers can see why a special rule was applied.
    """
    declared = data.get("category")
    name = data.get("name")
    text_parts = [str(part) for part in (declared, name) if isinstance(part, str) and part.strip()]
    text = " ".join(text_parts).casefold()
    exclusions = ("chocolate", "powder", "ice cream", "yogurt", "cheesecake", "buttermilk", "butterscotch")

    water = bool(re.search(r"\b(mineral waters?|spring waters?|table waters?)\b", text))
    if water or (re.search(r"\bwater\b", text) and "beverage" in text and not re.search(r"(flavou?r|juice|soda|sweet)", text)):
        return {"key": "beverage_water", "label": CATEGORY_LABELS["beverage_water"], "source": "declared" if declared else "name_heuristic", "beverage": True}

    beverage_patterns = (
        r"\bbeverages?\b", r"\bdrinks?\b", r"\bjuice\b", r"\bsoda\b",
        r"\bsoft drink\b", r"\bcarbonated\b", r"\bmilk drink\b", r"\bplant drink\b",
        r"\boat drink\b", r"\bsoya drink\b", r"\balmond drink\b",
    )
    if any(re.search(pattern, text) for pattern in beverage_patterns) and not any(word in text for word in exclusions):
        return {"key": "beverage", "label": CATEGORY_LABELS["beverage"], "source": "declared" if declared else "name_heuristic", "beverage": True}

    if re.search(r"\bcheese\b(?!cake)", text) and "cheese flavour" not in text:
        return {"key": "cheese", "label": CATEGORY_LABELS["cheese"], "source": "declared" if declared else "name_heuristic", "beverage": False}

    if re.search(r"\b(red meat|beef|veal|pork|lamb|mutton)\b", text) and "poultry" not in text:
        return {"key": "red_meat", "label": CATEGORY_LABELS["red_meat"], "source": "declared" if declared else "name_heuristic", "beverage": False}

    fat_terms = re.search(r"\b(oils?|fats?|ghee|butter|nuts?|seeds?|peanut butter)\b", text)
    if fat_terms and not re.search(r"\b(milk|yogurt|cheese|dessert)\b", text):
        return {"key": "fats_oils_nuts_seeds", "label": CATEGORY_LABELS["fats_oils_nuts_seeds"], "source": "declared" if declared else "name_heuristic", "beverage": False}

    return {"key": "general_food", "label": CATEGORY_LABELS["general_food"], "source": "declared_category" if declared else ("name_heuristic" if text else "default_general"), "beverage": False}


def _nns_status(data: dict[str, Any]) -> tuple[bool, str]:
    # shortcut: name/code matching covers common sweeteners only; upgrade when an authoritative INS list is available.
    if data.get("non_nutritive_sweeteners") is True:
        return True, "explicit"
    if data.get("non_nutritive_sweeteners") is False:
        return False, "explicit"
    tags = {str(tag).strip().upper() for tag in (data.get("additives_tags") or [])}
    if tags & NNS_CODES:
        return True, "additive_code_heuristic"
    text = " ".join(str(data.get("ingredients_text") or "").casefold().split())
    if any(term in text for term in NNS_TERMS):
        return True, "additive_name_heuristic"
    return False, "absent_or_unverified"


def _grade(score: int | None, category: dict[str, Any]) -> str | None:
    if category["key"] == "beverage_water":
        return "A"
    if score is None:
        return None
    if category["key"] == "beverage":
        if score <= 2:
            return "B"
        if score <= 6:
            return "C"
        if score <= 9:
            return "D"
        return "E"
    if category["key"] == "fats_oils_nuts_seeds":
        if score <= -6:
            return "A"
        if score <= 2:
            return "B"
        if score <= 10:
            return "C"
        if score <= 18:
            return "D"
        return "E"
    if score <= 0:
        return "A"
    if score <= 2:
        return "B"
    if score <= 10:
        return "C"
    if score <= 18:
        return "D"
    return "E"


def calculate_nutri_score(data: dict[str, Any]) -> dict[str, Any]:
    """Calculate an explainable Nutri-Score from values per 100 g or 100 ml."""
    data = data if isinstance(data, dict) else {}
    category = detect_category(data)
    result: dict[str, Any] = {
        "algorithm_version": ALGORITHM_VERSION,
        "status": "invalid_input",
        "category": category["label"],
        "category_key": category["key"],
        "category_source": category["source"],
        "reference_basis": REFERENCE_BASIS,
        "inputs": {},
        "normalized": {},
        "points": {"negative": {}, "positive": {}, "negative_total": None, "positive_total": None},
        "exceptions": [],
        "assumptions": [],
        "conversions": [],
        "warnings": [],
        "missing_inputs": [],
        "score": None,
        "grade": None,
    }

    if category["key"] == "beverage_water" and not any(
        data.get(key) is not None for key in ("energy_kj", "energy_kcal", "sugars", "saturated_fat", "salt", "sodium_mg")
    ):
        result["status"] = "calculated_water_rule"
        result["exceptions"].append("Mineral/table/spring water is grade A without a nutrition declaration.")
        result["grade"] = "A"
        result["points"]["negative_total"] = 0
        result["points"]["positive_total"] = 0
        result["score"] = 0
        return result

    raw: dict[str, float | None] = {}
    for canonical, keys in (
        ("energy_kj", ("energy_kj",)),
        ("energy_kcal", ("energy_kcal", "energy")),
        ("sugars", ("sugars", "sugar", "total_sugars")),
        ("saturated_fat", ("saturated_fat",)),
        ("total_fat", ("total_fat",)),
        ("sodium_mg", ("sodium_mg", "sodium")),
        ("salt", ("salt",)),
        ("fibre", ("fibre", "fiber")),
        ("protein", ("protein",)),
        ("fruit_vegetable_percent", ("fruit_vegetable_percent", "fruits_vegetables_percent", "fvl_percent")),
    ):
        value, source_key = _first(data, *keys)
        number, error = _coerce(value)
        if error:
            result["warnings"].append(error)
        raw[canonical] = number
        if number is not None:
            cap = CAPS.get(canonical)
            if cap is not None and number > cap:
                result["warnings"].append(f"{source_key or canonical} value {number} exceeds the plausible per-100 limit of {cap}.")
                raw[canonical] = None
            result["inputs"][canonical] = {"value": number, "source_key": source_key}

    if raw["saturated_fat"] is not None and raw["total_fat"] is not None and raw["saturated_fat"] > raw["total_fat"] + 0.01:
        result["warnings"].append("Saturated fat cannot exceed total fat; the values were rejected.")
        raw["saturated_fat"] = None
        raw["total_fat"] = None

    energy_kj = raw["energy_kj"]
    if energy_kj is None and raw["energy_kcal"] is not None:
        energy_kj = raw["energy_kcal"] * 4.184
        result["conversions"].append("Energy was converted from kcal to kJ using 1 kcal = 4.184 kJ.")
    salt = raw["salt"]
    if salt is None and raw["sodium_mg"] is not None:
        salt = raw["sodium_mg"] * 2.5 / 1000
        result["conversions"].append("Salt was estimated from sodium using salt = sodium x 2.5 / 1000.")

    # shortcut: missing optional fibre/protein/FVL scores as 0 with an explicit assumption; upgrade when a validated imputation source exists.
    normalized = {
        "energy_kj": energy_kj,
        "sugars": raw["sugars"],
        "saturated_fat": raw["saturated_fat"],
        "salt": salt,
        "fibre": raw["fibre"] or 0.0,
        "protein": raw["protein"] or 0.0,
        "fruit_vegetable_percent": raw["fruit_vegetable_percent"] or 0.0,
    }
    result["normalized"] = {key: value for key, value in normalized.items()}

    missing = [key for key in MANDATORY_INPUTS if normalized.get(key) is None]
    if missing:
        result["status"] = "incomplete_data"
        result["missing_inputs"] = missing
        result["warnings"].append(
            "A final Nutri-Score grade was not calculated because " + ", ".join(missing) + " is unavailable."
        )
        return result

    nns_present, nns_basis = _nns_status(data)
    if nns_basis != "absent_or_unverified":
        result["exceptions"].append(f"Non-nutritive sweeteners detected ({nns_basis}); +4 negative points for beverages.")
    elif category["beverage"]:
        result["warnings"].append("Non-nutritive sweetener status could not be verified; no +4 points were added.")

    beverage = category["beverage"]
    if category["key"] == "fats_oils_nuts_seeds":
        negative_thresholds = {
            "energy_from_saturates": ENERGY_FAT_SFA,
            "sugars": SUGARS_GENERAL,
            "sfa_ratio": SFA_RATIO_FAT,
            "salt": SALT_GENERAL,
        }
    elif beverage:
        negative_thresholds = {
            "energy": ENERGY_BEVERAGE,
            "sugars": SUGARS_BEVERAGE,
            "saturated_fat": SFA_BEVERAGE,
            "salt": SALT_GENERAL,
        }
    else:
        negative_thresholds = {
            "energy": ENERGY_GENERAL,
            "sugars": SUGARS_GENERAL,
            "saturated_fat": SFA_GENERAL,
            "salt": SALT_GENERAL,
        }

    negative_inputs = {
        "energy": normalized["energy_kj"],
        "sugars": normalized["sugars"],
        "saturated_fat": normalized["saturated_fat"],
        "salt": normalized["salt"],
    }
    if category["key"] == "fats_oils_nuts_seeds":
        energy_from_saturates = normalized["saturated_fat"] * 37
        sfa_ratio = (
            (normalized["saturated_fat"] / raw["total_fat"] * 100)
            if raw["total_fat"] and raw["total_fat"] > 0 else None
        )
        negative_values = {
            "energy_from_saturates": energy_from_saturates,
            "sugars": normalized["sugars"],
            "sfa_ratio": sfa_ratio,
            "salt": normalized["salt"],
        }
        result["normalized"]["energy_from_saturates_kj"] = energy_from_saturates
        result["normalized"]["sfa_to_total_fat_percent"] = sfa_ratio
    else:
        negative_values = negative_inputs

    negative_points: dict[str, int | None] = {}
    for component, value in negative_values.items():
        if value is None:
            negative_points[component] = None
            continue
        if component == "sfa_ratio":
            # The saturated-fat ratio bands are "<10", "<16", ..., so a value
            # equal to a boundary moves into the higher point band.
            negative_points[component] = bisect_right(negative_thresholds[component], value)
        else:
            negative_points[component] = _points(value, negative_thresholds[component])
        result["points"]["negative"][component] = {
            "value": round(value, 4),
            "points": negative_points[component],
            "thresholds": negative_thresholds[component],
        }
    if category["key"] == "fats_oils_nuts_seeds" and negative_points.get("sfa_ratio") is None:
        result["warnings"].append("Saturated-fat-to-total-fat ratio is unavailable; the fats-category ratio points were treated as 0.")
        negative_points["sfa_ratio"] = 0
        result["assumptions"].append("Missing total fat meant 0 saturated-fat-ratio points in the fats/oils category.")
    if beverage and nns_present:
        negative_points["nns"] = 4
        result["points"]["negative"]["nns"] = {"value": "present", "points": 4}
    negative_total = sum(int(value or 0) for value in negative_points.values())

    positive_thresholds = {
        "protein": PROTEIN_BEVERAGE if beverage else PROTEIN_GENERAL,
        "fibre": FIBRE_BEVERAGE if beverage else FIBRE_GENERAL,
        "fruit_vegetable_percent": FVL_BEVERAGE if beverage else FVL_GENERAL,
    }
    positive_values = {
        "protein": normalized["protein"],
        "fibre": normalized["fibre"],
        "fruit_vegetable_percent": normalized["fruit_vegetable_percent"],
    }
    positive_points = {
        "protein": _points(positive_values["protein"], positive_thresholds["protein"]),
        "fibre": _points(positive_values["fibre"], positive_thresholds["fibre"]),
        "fruit_vegetable_percent": _points(
            positive_values["fruit_vegetable_percent"], positive_thresholds["fruit_vegetable_percent"]
        ),
    }
    if positive_points["fruit_vegetable_percent"] > 3:
        raise AssertionError("FVL point table must never return point 3 or 4")
    positive_points["fruit_vegetable_percent"] = (
        FVL_POINTS_BEVERAGE if beverage else FVL_POINTS_GENERAL
    )[positive_points["fruit_vegetable_percent"]]
    for component, value in positive_values.items():
        result["points"]["positive"][component] = {
            "value": round(value, 4),
            "points": positive_points[component],
            "thresholds": positive_thresholds[component],
        }
        if component == "fruit_vegetable_percent":
            result["points"]["positive"][component]["point_map"] = (
                FVL_POINTS_BEVERAGE if beverage else FVL_POINTS_GENERAL
            )
    for key in ("fibre", "protein", "fruit_vegetable_percent"):
        if raw[key] is None:
            result["assumptions"].append(f"{key} was not provided; 0 positive points were assigned.")

    if category["key"] == "red_meat" and positive_points["protein"] > 2:
        positive_points["protein"] = 2
        result["points"]["positive"]["protein"]["points"] = 2
        result["exceptions"].append("Red meat protein points are capped at 2.")
    if category["key"] == "cheese":
        result["exceptions"].append("Cheese protein points are always counted.")
    protein_used = True
    if category["key"] == "fats_oils_nuts_seeds":
        result["exceptions"].append("Fats/oils/nuts/seeds use the saturated-fat energy table.")
        if negative_total >= 7:
            positive_points["protein"] = 0
            protein_used = False
            result["points"]["positive"]["protein"]["points"] = 0
            result["exceptions"].append("Protein points are excluded for this category when negative points reach 7.")
    elif beverage:
        result["exceptions"].append("Beverages use the beverage algorithm; only water can be grade A.")
    elif negative_total >= 11:
        positive_points["protein"] = 0
        protein_used = False
        result["points"]["positive"]["protein"]["points"] = 0
        result["exceptions"].append("Protein points are excluded when negative points reach 11.")

    positive_total = sum(positive_points.values())
    score = negative_total - positive_total
    result["points"]["negative_total"] = negative_total
    result["points"]["positive_total"] = positive_total
    result["points"]["protein_points_used"] = protein_used
    result["score"] = score
    result["grade"] = _grade(score, category)
    result["status"] = (
        "calculated_with_assumptions" if result["assumptions"] else "calculated"
    )
    return result
