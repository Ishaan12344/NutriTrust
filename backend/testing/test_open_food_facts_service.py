import unittest
from unittest.mock import AsyncMock, patch

import httpx

from open_food_facts_service import (
    _clean_barcode,
    _extract_nutrition_per_100g,
    _normalize_product,
    fetch_open_food_facts_product,
)


class BarcodeTests(unittest.TestCase):
    def test_barcode_cleaning(self):
        self.assertEqual(_clean_barcode(" 3017624010701 "), "3017624010701")

    def test_rejects_non_numeric_barcode(self):
        with self.assertRaises(ValueError):
            _clean_barcode("12AB34")

    def test_nutrition_mapping_preserves_missing_values(self):
        mapped = _extract_nutrition_per_100g({"nutriments": {
            "fat_100g": 10,
            "sodium_100g": 0.4,
            "sodium_unit": "g",
            "calcium_100g": 0.12,
            "calcium_unit": "g",
            "iron_100g": 250,
            "iron_unit": "µg",
            "sugars_100g": 5,
        }})
        self.assertEqual(mapped["total_fat"]["value"], 10.0)
        self.assertEqual(mapped["sodium"]["value"], 400.0)
        self.assertEqual(mapped["calcium"]["value"], 120.0)
        self.assertEqual(mapped["iron"]["value"], 0.25)
        self.assertEqual(mapped["sodium"]["basis"], "per_100g")
        self.assertNotIn("protein", mapped)

    def test_added_sugar_modifier_is_preserved(self):
        mapped = _extract_nutrition_per_100g({"nutriments": {
            "sugars_100g": 18.8,
            "added-sugars_100g": 0,
            "added-sugars_modifier": "~",
        }})
        self.assertEqual(mapped["added_sugar"]["value"], 0.0)
        self.assertEqual(mapped["added_sugar"]["status"], "approximate")
        self.assertEqual(mapped["added_sugar"]["modifier"], "~")

    def test_unsuffixed_fields_require_explicit_100g_basis(self):
        without_basis = _extract_nutrition_per_100g({
            "nutriments": {"fat": 10, "energy-kcal": 200},
        })
        with_basis = _extract_nutrition_per_100g({
            "nutrition_data_per": "100g",
            "nutriments": {"fat": 10, "energy_100g": 840, "energy_unit": "kJ"},
        })
        self.assertEqual(without_basis, {})
        self.assertEqual(with_basis["total_fat"]["value"], 10)
        self.assertAlmostEqual(with_basis["energy_kcal"]["value"], 200.7648)

    def test_explicit_open_food_facts_serving_values_are_kept_separate(self):
        product = {
            "nutriments": {
                "energy-kcal_serving": 172,
                "energy-kcal_unit": "kcal",
                "proteins_serving": 4.5,
                "proteins_unit": "g",
                "energy-kcal_100g": 430,
                "proteins_100g": 11.25,
            }
        }
        serving = __import__("open_food_facts_service")._extract_nutrition_per_serving(product)
        per_100g = _extract_nutrition_per_100g(product)
        self.assertEqual(serving["energy_kcal"]["value"], 172)
        self.assertEqual(serving["energy_kcal"]["basis"], "per_serving")
        self.assertEqual(per_100g["energy_kcal"]["value"], 430)

    def test_v2_fallback_fills_gaps_without_overwriting_v3_values(self):
        v3 = self._response({"status": "success", "product": {
            "code": "1234567890123", "product_name": "Example",
            "nutriments": {"energy-kcal_100g": 200},
        }})
        v2 = self._response({"status": 1, "product": {"code": "1234567890123", "nutriments": {
            "energy-kcal_100g": 210, "fat_100g": 8,
        }}})
        with patch("open_food_facts_service.httpx.AsyncClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.get = AsyncMock(side_effect=[v3, v2])
            result = __import__("asyncio").run(fetch_open_food_facts_product("1234567890123"))
        self.assertEqual(result["nutrition_per_100g"]["energy_kcal"]["value"], 200)
        self.assertEqual(result["nutrition_per_100g"]["energy_kcal"]["source"], "open_food_facts")
        self.assertEqual(result["nutrition_per_100g"]["total_fat"]["value"], 8)
        self.assertEqual(result["nutrition_per_100g"]["total_fat"]["source"], "open_food_facts_v2_fallback")

    def test_normalized_product_fields(self):
        result = _normalize_product({
            "code": "1234567890123",
            "product_name": "Example",
            "ingredients_text": "Oats, sugar",
            "allergens_tags": ["en:gluten"],
            "additives_n": 1,
            "nova_group": 3,
            "nutriments": {"proteins_100g": 8},
        }, "1234567890123")
        self.assertEqual(result["product_name"], "Example")
        self.assertEqual(result["nutrition_per_100g"]["protein"]["value"], 8.0)
        self.assertEqual(result["allergens_tags"], ["en:gluten"])
        self.assertNotIn("debug_raw_nutriments", result)

    @staticmethod
    def _response(body, status_code=200):
        return httpx.Response(
            status_code,
            json=body,
            request=httpx.Request("GET", "https://world.openfoodfacts.org/test"),
        )

    def test_successful_v3_retrieval_uses_v3_nutrition(self):
        response = self._response({"status": "success", "product": {
            "code": "1234567890123", "product_name": "Example",
            "nutriments": {"energy-kcal_100g": 100, "energy-kcal_unit": "kcal"},
        }})
        with patch("open_food_facts_service.httpx.AsyncClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.get = AsyncMock(return_value=response)
            result = __import__("asyncio").run(fetch_open_food_facts_product("1234567890123"))
        self.assertEqual(client.get.await_count, 2)
        self.assertEqual(result["nutrition_source"], "open_food_facts_v3.6")
        self.assertEqual(result["nutrition_per_100g"]["energy_kcal"]["value"], 100.0)

    def test_empty_v3_nutrition_falls_back_to_v2(self):
        v3 = self._response({"status": "success", "product": {
            "code": "3017624010701", "product_name": "Nutella", "nutriments": {},
        }})
        v2 = self._response({"status": 1, "product": {"code": "3017624010701", "nutriments": {
            "energy-kcal_100g": 539, "fat_100g": 30.9, "sodium_100g": 0.043,
            "sodium_unit": "g", "proteins_100g": 6.3,
        }}})
        with patch("open_food_facts_service.httpx.AsyncClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.get = AsyncMock(side_effect=[v3, v2])
            result = __import__("asyncio").run(fetch_open_food_facts_product("3017624010701"))
        self.assertEqual(client.get.await_count, 2)
        self.assertEqual(result["product_name"], "Nutella")
        self.assertEqual(result["nutrition_source"], "open_food_facts_v2_fallback")
        self.assertEqual(result["nutrition_per_100g"]["energy_kcal"]["value"], 539.0)
        self.assertEqual(result["nutrition_per_100g"]["sodium"]["value"], 43.0)
        self.assertNotIn("debug_raw_nutriments", result)

    def test_missing_nutrition_stays_missing(self):
        v3 = self._response({"status": "success", "product": {"code": "1234567890123", "nutriments": {}}})
        v2 = self._response({"status": 1, "product": {"code": "1234567890123", "nutriments": {}}})
        with patch("open_food_facts_service.httpx.AsyncClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.get = AsyncMock(side_effect=[v3, v2])
            result = __import__("asyncio").run(fetch_open_food_facts_product("1234567890123"))
        self.assertEqual(result["nutrition_per_100g"], {})
        self.assertNotIn("nutrition", result["available_fields"])

    def test_invalid_barcode_does_not_make_request(self):
        with patch("open_food_facts_service.httpx.AsyncClient") as client_cls:
            with self.assertRaises(ValueError):
                __import__("asyncio").run(fetch_open_food_facts_product("12AB34"))
        client_cls.assert_not_called()

    def test_primary_api_failure_propagates(self):
        response = self._response({"error": "server error"}, status_code=503)
        with patch("open_food_facts_service.httpx.AsyncClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.get = AsyncMock(return_value=response)
            with self.assertRaises(httpx.HTTPStatusError):
                __import__("asyncio").run(fetch_open_food_facts_product("1234567890123"))

    def test_fallback_api_failure_keeps_product_and_missing_nutrition(self):
        v3 = self._response({"status": "success", "product": {
            "code": "1234567890123", "product_name": "Example", "nutriments": {},
        }})
        v2 = self._response({"error": "unavailable"}, status_code=503)
        with patch("open_food_facts_service.httpx.AsyncClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.get = AsyncMock(side_effect=[v3, v2])
            result = __import__("asyncio").run(fetch_open_food_facts_product("1234567890123"))
        self.assertTrue(result["found"])
        self.assertEqual(result["product_name"], "Example")
        self.assertEqual(result["nutrition_per_100g"], {})

    def test_product_not_found(self):
        response = httpx.Response(
            200,
            json={"status": "failure", "status_verbose": "product not found"},
            request=httpx.Request("GET", "https://world.openfoodfacts.org"),
        )
        with patch("open_food_facts_service.httpx.AsyncClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.get = AsyncMock(return_value=response)
            result = __import__("asyncio").run(fetch_open_food_facts_product("1234567890123"))
        self.assertFalse(result["found"])


if __name__ == "__main__":
    unittest.main()
