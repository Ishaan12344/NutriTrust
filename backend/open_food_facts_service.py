"""Read-only Open Food Facts API client for NutriTrust.

Uses the current Open Food Facts API v3.6 product-by-barcode endpoint.
No API key is required for reads; a descriptive User-Agent is required/recommended.
"""
from __future__ import annotations

import os
import re
from typing import Any

import httpx

from app_config import get_settings

BASE_URL = "https://world.openfoodfacts.org/api/v3.6/product"
NUTRITION_FALLBACK_URL = "https://world.openfoodfacts.org/api/v2/product"

FIELDS = ",".join([
    "code",
    "product_name",
    "product_name_en",
    "brands",
    "quantity",
    "product_quantity",
    "product_quantity_unit",
    "nutrition_data_per",
    "categories",
    "categories_tags",
    "labels_tags",
    "ingredients_text",
    "ingredients_text_en",
    "ingredients",
    "allergens",
    "allergens_tags",
    "traces",
    "traces_tags",
    "additives_n",
    "additives_tags",
    "nova_group",
    "nutriscore_grade",
    "nutrition_grades",
    "nutriscore_version",
    "nutriments",
    "image_front_url",
    "image_nutrition_url",
    "environmental_score_grade",
    "data_quality_errors_tags",
])

# Open Food Facts uses a public API. Set this to an identifiable app/contact string
# before deployment; do not impersonate another application.
DEFAULT_USER_AGENT = "NutriTrust/0.1 (contact: configure-NUTRITRUST_CONTACT)"

def _clean_barcode(barcode: str) -> str:
    code = re.sub(r"[\s-]", "", barcode or "")
    if not code or not code.isdigit():
        raise ValueError("Barcode must contain digits only.")
    if not 6 <= len(code) <= 14:
        raise ValueError("Barcode length must be between 6 and 14 digits.")
    return code

def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None

def _first_present(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None and value != "":
            return value
    return None

def _extract_nutrition_per_100g(product: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map OFF nutriments to NutriTrust names without treating missing data as zero.

    OFF nutrient values are generally per 100 g for solid foods. Unit conversions
    below follow the nutrient units used by the OFF nutriments schema.
    """
    raw = product.get("nutriments")
    if not isinstance(raw, dict):
        raw = {}

    specs: dict[str, tuple[str, str, str, float]] = {
        "energy_kcal": ("energy-kcal_100g", "kcal", "energy-kcal_unit", 1.0),
        "total_fat": ("fat_100g", "g", "fat_unit", 1.0),
        "saturated_fat": ("saturated-fat_100g", "g", "saturated-fat_unit", 1.0),
        "trans_fat": ("trans-fat_100g", "g", "trans-fat_unit", 1.0),
        "cholesterol": ("cholesterol_100g", "mg", "cholesterol_unit", 1.0),
        "sodium": ("sodium_100g", "mg", "sodium_unit", 1000.0),
        "salt": ("salt_100g", "g", "salt_unit", 1.0),
        "total_carbohydrate": ("carbohydrates_100g", "g", "carbohydrates_unit", 1.0),
        "fiber": ("fiber_100g", "g", "fiber_unit", 1.0),
        "sugar": ("sugars_100g", "g", "sugars_unit", 1.0),
        "added_sugar": ("added-sugars_100g", "g", "added-sugars_unit", 1.0),
        "protein": ("proteins_100g", "g", "proteins_unit", 1.0),
        "calcium": ("calcium_100g", "mg", "calcium_unit", 1.0),
        "iron": ("iron_100g", "mg", "iron_unit", 1.0),
        "potassium": ("potassium_100g", "mg", "potassium_unit", 1.0),
    }

    basis = str(product.get("nutrition_data_per") or "").strip().lower().replace(" ", "")
    result: dict[str, dict[str, Any]] = {}
    for name, (key, unit, unit_key, default_multiplier) in specs.items():
        value = _number(raw.get(key))
        source_key = key
        if value is None and key.endswith("_100g"):
            underscore_key = key.replace("-", "_")
            if _number(raw.get(underscore_key)) is not None:
                source_key = underscore_key
                value = _number(raw.get(underscore_key))
        if name == "energy_kcal" and value is None:
            energy_kj = _number(raw.get("energy-kj_100g")) or _number(raw.get("energy_kj_100g"))
            if energy_kj is not None:
                value = energy_kj / 4.184
                source_key = "energy-kj_100g"
        # Unsuffixed values are accepted only when OFF explicitly declares a 100 g basis.
        if value is None and basis in {"100g", "100g/ml"}:
            base = key.removesuffix("_100g")
            for alias in (base, base.replace("-", "_")):
                if _number(raw.get(alias)) is not None:
                    source_key = alias
                    value = _number(raw.get(alias))
                    break
        if name == "energy_kcal" and value is None:
            energy_kj = _number(raw.get("energy_100g")) if basis == "100g" else None
            if energy_kj is not None:
                energy_unit = str(raw.get("energy_unit") or "kj").casefold()
                value = energy_kj / 4.184 if energy_unit in {"kj", "kilojoule", "kilojoules"} else energy_kj
                source_key = "energy_100g"
        if value is not None:
            multiplier = default_multiplier
            if unit == "mg":
                source_unit = str(raw.get(unit_key, "g" if name == "sodium" else "mg")).lower()
                if source_unit in {"µg", "μg", "ug"}:
                    multiplier = 0.001
                elif source_unit == "g":
                    multiplier = 1000.0
                else:
                    multiplier = 1.0
            item = {"value": round(value * multiplier, 4), "unit": unit,
                    "basis": "per_100g", "source": "open_food_facts",
                    "evidence": "reported", "status": "reported"}
            modifier = raw.get(f"{source_key.removesuffix('_100g')}_modifier")
            if modifier:
                item["modifier"] = modifier
                item["status"] = "approximate" if str(modifier).strip() != "" else "reported"
            result[name] = item
    return result


def _extract_nutrition_per_serving(product: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map OFF's explicit `_serving` fields; never derive them from per-100-g data."""
    raw = product.get("nutriments")
    if not isinstance(raw, dict):
        return {}
    serving_raw = {}
    for key, value in raw.items():
        if key.endswith("_serving"):
            serving_raw[key.removesuffix("_serving") + "_100g"] = value
        elif key.endswith("_unit"):
            serving_raw[key] = value
        elif key.endswith("_modifier"):
            serving_raw[key] = value
    mapped = _extract_nutrition_per_100g({"nutriments": serving_raw, "nutrition_data_per": "serving"})
    for item in mapped.values():
        item["basis"] = "per_serving"
    return mapped

def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None and str(item).strip()]

def _normalize_product(product: dict[str, Any], requested_barcode: str) -> dict[str, Any]:
    nutriments = product.get("nutriments")
    if not isinstance(nutriments, dict):
        nutriments = {}

    product_name = _first_present(product, "product_name", "product_name_en")
    ingredients_text = _first_present(product, "ingredients_text", "ingredients_text_en")
    allergens = product.get("allergens")
    traces = product.get("traces")

    return {
        "source": "open_food_facts",
        "barcode": str(_first_present(product, "code", "id", "_id") or requested_barcode),
        "product_name": product_name,
        "brands": product.get("brands"),
        "quantity": product.get("quantity"),
        "product_quantity": _number(product.get("product_quantity")),
        "product_quantity_unit": product.get("product_quantity_unit"),
        "categories": product.get("categories"),
        "categories_tags": _string_list(product.get("categories_tags")),
        "labels_tags": _string_list(product.get("labels_tags")),
        "ingredients_text": ingredients_text,
        "ingredients": product.get("ingredients") if isinstance(product.get("ingredients"), list) else [],
        "allergens": allergens,
        "allergens_tags": _string_list(product.get("allergens_tags")),
        "traces": traces,
        "traces_tags": _string_list(product.get("traces_tags")),
        "additives_count": _number(product.get("additives_n")),
        "additives_tags": _string_list(product.get("additives_tags")),
        "additives_available": "additives_tags" in product or "additives_n" in product,
        "nova_group": _number(product.get("nova_group")),
        "nova_source": "open_food_facts" if product.get("nova_group") is not None else None,
        "nutriscore_grade": _first_present(product, "nutriscore_grade", "nutrition_grades"),
        "nutriscore_version": product.get("nutriscore_version"),
        "environmental_score_grade": product.get("environmental_score_grade"),
        "image_front_url": product.get("image_front_url"),
        "image_nutrition_url": product.get("image_nutrition_url"),
        "nutrition_per_100g": _extract_nutrition_per_100g(product),
        "nutrition_per_serving": _extract_nutrition_per_serving(product),
        "nutrition_basis": "per_100g",
        "nutrition_source": "open_food_facts_v3.6" if (_extract_nutrition_per_100g(product) or _extract_nutrition_per_serving(product)) else None,
        "data_quality_errors": _string_list(product.get("data_quality_errors_tags")),
        "available_fields": [
            key for key, value in {
                "product_name": product_name,
                "ingredients_text": ingredients_text,
                "allergens": allergens,
                "nutrition": _extract_nutrition_per_100g(product),
                "nutrition_per_serving": _extract_nutrition_per_serving(product),
                "nova_group": product.get("nova_group"),
                "nutriscore_grade": _first_present(product, "nutriscore_grade", "nutrition_grades"),
            }.items() if value is not None and value != {} and value != ""
        ],
    }

async def fetch_open_food_facts_product(
    barcode: str,
    *,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Fetch a single product by barcode and return a normalized result.

    Raises ValueError for invalid barcode; httpx errors for transport failures.
    Product-not-found is returned as {"found": False, ...}, not raised.
    """
    code = _clean_barcode(barcode)
    timeout_seconds = timeout_seconds if timeout_seconds is not None else get_settings().open_food_facts_timeout_seconds
    user_agent = os.getenv("NUTRITRUST_OFF_USER_AGENT", DEFAULT_USER_AGENT)
    if "configure-NUTRITRUST_CONTACT" in user_agent:
        # Still usable during local development, but configure a real contact before release.
        user_agent = "NutriTrust/0.1 (local development; contact: not-configured)"

    url = f"{BASE_URL}/{code}.json"
    headers = {"User-Agent": user_agent, "Accept": "application/json"}

    async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
        response = await client.get(url, params={"fields": FIELDS}, headers=headers)

    if response.status_code == 404:
        return {
            "source": "open_food_facts",
            "found": False,
            "barcode": code,
            "message": "Product was not found in Open Food Facts.",
        }

    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("Open Food Facts returned a non-JSON response.") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("Open Food Facts returned an unexpected response format.")

    # API v3 responses have a status and product object. The API may return HTTP 200
    # for some non-success responses, so inspect the body as well as the HTTP status.
    product = payload.get("product")
    status = payload.get("status")
    if not isinstance(product, dict) or status in {"failure", "not_found", 0, "0"}:
        return {
            "source": "open_food_facts",
            "found": False,
            "barcode": code,
            "message": payload.get("status_verbose") or "Product was not found in Open Food Facts.",
        }

    normalized = _normalize_product(product, code)
    # Query v2 when v3 is empty or lacks mapped nutrients; preserve every v3
    # value and use v2 only to fill absent canonical keys.
    expected_nutrients = {
        "energy_kcal", "total_fat", "saturated_fat", "total_carbohydrate",
        "sugar", "added_sugar", "protein", "sodium", "salt", "fiber",
    }
    if not expected_nutrients.issubset(normalized["nutrition_per_100g"]):
        fallback_url = f"{NUTRITION_FALLBACK_URL}/{code}.json"
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client:
                fallback_response = await client.get(
                    fallback_url,
                    params={"fields": "code,nutriments,nutrition_data_per"},
                    headers=headers,
                )
            fallback_response.raise_for_status()
            fallback_payload = fallback_response.json()
            fallback_product = fallback_payload.get("product") if isinstance(fallback_payload, dict) else None
            fallback_nutriments = fallback_product.get("nutriments") if isinstance(fallback_product, dict) else None
            if isinstance(fallback_nutriments, dict):
                fallback_nutrition = _extract_nutrition_per_100g({
                    "nutriments": fallback_nutriments,
                    "nutrition_data_per": fallback_product.get("nutrition_data_per"),
                })
                if fallback_nutrition:
                    current = normalized["nutrition_per_100g"]
                    for nutrient, item in fallback_nutrition.items():
                        if nutrient not in current:
                            item["source"] = "open_food_facts_v2_fallback"
                            item["evidence"] = "reported"
                            current[nutrient] = item
                    if any(item.get("source") == "open_food_facts_v2_fallback" for item in current.values()):
                        normalized["nutrition_source"] = (
                            "open_food_facts_v3.6+v2_fallback"
                            if any(item.get("source") == "open_food_facts_v3.6" for item in current.values())
                            else "open_food_facts_v2_fallback"
                        )
                    if "nutrition" not in normalized["available_fields"]:
                        normalized["available_fields"].append("nutrition")
        except (httpx.HTTPError, ValueError):
            # Keep product information from v3 even if the optional nutrition fallback fails.
            pass
    normalized["found"] = True
    normalized["api_status"] = status
    return normalized
