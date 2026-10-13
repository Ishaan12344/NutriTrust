"""
Barcode Service
Looks up product data from Open Food Facts API by barcode.
"""

import httpx
from app.config import OPEN_FOOD_FACTS_API


async def lookup(barcode: str) -> dict | None:
    """
    Look up a product by barcode from Open Food Facts.
    Returns structured product data or None if not found.
    """
    url = f"{OPEN_FOOD_FACTS_API}/{barcode}.json"
    headers = {
        "User-Agent": "NutriTrust/1.0 (https://github.com/nutritrust; contact@nutritrust.com)"
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, headers=headers)
            data = response.json()

            if data.get("status") != 1 or "product" not in data:
                return None

            product = data["product"]
            nutriments = product.get("nutriments", {})

            # Extract sodium: try sodium_100g first, fallback to salt_100g / 2.5
            sodium_val = nutriments.get("sodium_100g")
            if sodium_val is None and "salt_100g" in nutriments:
                salt_val = nutriments.get("salt_100g")
                if salt_val is not None:
                    sodium_val = float(salt_val) / 2.5

            result = {
                "product": {
                    "name": product.get("product_name") or product.get("product_name_en") or "Unknown Product",
                    "brand": product.get("brands") or "Unknown Brand",
                    "barcode": barcode,
                    "categories": product.get("categories") or "N/A",
                    "image_url": product.get("image_url") or "",
                    "source": "openfoodfacts",
                },
                "nutrition_per_100g": {
                    "energy_kcal": _safe_float(nutriments.get("energy-kcal_100g") or nutriments.get("energy-kcal")),
                    "total_fat": _safe_float(nutriments.get("fat_100g")),
                    "saturated_fat": _safe_float(nutriments.get("saturated-fat_100g")),
                    "trans_fat": _safe_float(nutriments.get("trans-fat_100g")),
                    "sugar": _safe_float(nutriments.get("sugars_100g")),
                    "sodium": _safe_float(sodium_val, multiplier=1000),  # Convert g to mg
                    "fiber": _safe_float(nutriments.get("fiber_100g")),
                    "protein": _safe_float(nutriments.get("proteins_100g")),
                },
                "ingredients_text": product.get("ingredients_text") or product.get("ingredients_text_en") or "",
                "additives_tags": [
                    tag.replace("en:", "").upper()
                    for tag in product.get("additives_tags", [])
                ],
                "nova_group": product.get("nova_group"),
            }


            return result

    except (httpx.RequestError, httpx.TimeoutException, Exception) as e:
        print(f"[Barcode Service] Error looking up {barcode}: {e}")
        return None


def _safe_float(value, multiplier: float = 1.0) -> float:
    """Safely convert a value to float, returning 0.0 if invalid."""
    try:
        if value is None:
            return 0.0
        return round(float(value) * multiplier, 2)
    except (ValueError, TypeError):
        return 0.0
