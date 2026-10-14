import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from main import app
from scoring_service import rate


COMPLETE_NUTRITION = {
    "energy_kcal": 431,
    "total_fat": 14.6,
    "saturated_fat": 8.2,
    "sugar": 18.8,
    "sodium": 414,
    "fiber": 1.6,
    "protein": 20.5,
}


class ScoringServiceTests(unittest.TestCase):
    def test_complete_product_returns_all_weighted_components(self):
        result = rate({
            "nutrition_per_100g": COMPLETE_NUTRITION,
            "ingredients_text": "Skimmed Milk Powder, Refined Wheat Flour, E500",
            "additives_tags": ["en:e500"],
            "additives_available": True,
            "additives_count": 1,
            "nova_group": 4,
            "nova_source": "open_food_facts",
        })

        self.assertEqual(result["data_sufficiency"]["status"], "partial")
        self.assertEqual(result["data_sufficiency"]["scoring_eligibility"], "eligible_provisional")
        self.assertIsInstance(result["scores"]["overall"], int)
        self.assertEqual(result["scores"]["nova_processing"]["source"], "open_food_facts")
        self.assertIn("traffic_lights", result["scores"]["nutrient_limits"])
        self.assertEqual(result["scores"]["additive_safety"]["status"], "known")

    def test_missing_required_nutrients_do_not_become_zero_or_score(self):
        result = rate({
            "nutrition_per_100g": {"energy_kcal": 100, "total_fat": 1, "saturated_fat": 0},
            "ingredients_text": "flour",
            "additives_available": True,
        })

        self.assertIsNone(result["scores"]["overall"])
        self.assertEqual(result["data_sufficiency"]["status"], "partial")
        self.assertEqual(result["data_sufficiency"]["scoring_eligibility"], "ineligible")
        self.assertIn("sugar", result["data_sufficiency"]["missing"])
        self.assertIn("sodium", result["data_sufficiency"]["missing"])

    def test_genuine_zero_is_retained_as_measured(self):
        nutrition = dict(COMPLETE_NUTRITION, sugar=0, sodium=0)
        result = rate({
            "nutrition_per_100g": nutrition,
            "ingredients_text": "flour, E500",
            "additives_available": True,
        })

        self.assertEqual(result["data_sufficiency"]["status"], "partial")
        self.assertEqual(result["nutrition_per_100g"]["sugar"], 0)
        self.assertEqual(result["nutrition_per_100g"]["sodium"], 0)

    def test_missing_additives_are_not_called_safe(self):
        result = rate({
            "nutrition_per_100g": COMPLETE_NUTRITION,
            "ingredients_text": "flour",
            "additives_available": False,
        })

        self.assertIsNone(result["scores"]["overall"])
        self.assertEqual(result["scores"]["additive_safety"]["status"], "unavailable")
        self.assertIn("additive information", result["data_sufficiency"]["missing"])

    def test_unknown_nova_is_unavailable_despite_markers(self):
        result = rate({
            "nutrition_per_100g": COMPLETE_NUTRITION,
            "ingredients_text": (
                "flour, hydrogenated, maltodextrin, emulsifier, stabilizer, "
                "flavouring, artificial colour"
            ),
            "additives_tags": ["en:e500"],
            "additives_available": True,
            "additives_count": 1,
        })

        self.assertEqual(result["scores"]["nova_processing"]["source"], "unavailable")
        self.assertIsNone(result["scores"]["nova_processing"]["nova_group"])
        self.assertIsNone(result["scores"]["overall"])

    def test_gulab_jamun_regression_score_has_breakdown(self):
        result = rate({
            "nutrition_per_100g": dict(COMPLETE_NUTRITION, total_fat=14.6,
                                       total_carbohydrate=54.6, fiber=1.6, protein=20.5),
            "ingredients_text": "Skimmed milk powder, refined wheat flour, hydrogenated vegetable oils, sodium bicarbonate",
            "additives_tags": ["en:e500"],
            "additives_available": True,
            "additives_count": 1,
            "nova_group": 4,
            "nova_source": "open_food_facts",
        })
        self.assertEqual(result["scores"]["overall"], 48)
        self.assertEqual(result["component_scores"], {
            "nutrient_quality": 50,
            "nova_processing": 10,
            "nutrient_limits": 50,
            "additive_safety": 100,
        })
        self.assertEqual(sum(result["contributions"].values()), 47.5)
        self.assertEqual(result["scores"]["nutrient_limits"]["traffic_lights"]["salt"]["value"], 1.035)
        self.assertNotIn("added_sugar", result["nutrition_per_100g"])
        self.assertEqual(result["data_sufficiency"]["status"], "partial")
        self.assertEqual(result["data_sufficiency"]["score_confidence"], "not_calibrated")

    def test_material_nutrition_conflict_prevents_overall_score(self):
        result = rate({
            "nutrition_per_100g": COMPLETE_NUTRITION,
            "ingredients_text": "flour",
            "additives_tags": ["en:e500"],
            "additives_available": True,
            "nova_group": 4,
            "nova_source": "open_food_facts",
            "nutrition_conflicts": [{"nutrient": "sugar", "ocr_value": 18, "open_food_facts_value": 22}],
        })
        self.assertIsNone(result["scores"]["overall"])
        self.assertIn("unresolved conflicts in scored nutrients", result["data_sufficiency"]["missing"])

    def test_unknown_additive_code_does_not_receive_perfect_score(self):
        result = rate({
            "nutrition_per_100g": COMPLETE_NUTRITION,
            "ingredients_text": "flour, E9999",
            "additives_tags": ["en:e9999"],
            "additives_available": True,
            "additives_count": 1,
            "nova_group": 4,
            "nova_source": "open_food_facts",
        })
        self.assertIsNone(result["scores"]["overall"])
        self.assertIsNone(result["scores"]["additive_safety"]["score"])
        self.assertEqual(result["scores"]["additive_safety"]["unverified_additives"], ["E9999"])

    def test_beverage_per_100g_values_are_not_given_solid_food_colors(self):
        result = rate({
            "product": {"categories": "Beverages"},
            "nutrition_per_100g": COMPLETE_NUTRITION,
            "ingredients_text": "water, flavoring",
            "additives_tags": [],
            "additives_available": True,
            "additives_count": 0,
            "nova_group": 4,
            "nova_source": "open_food_facts",
        })
        lights = result["scores"]["nutrient_limits"]["traffic_lights"]
        self.assertTrue(all(item["verified"] is False for item in lights.values()))
        self.assertEqual(result["scores"]["nutrient_limits"]["ruleset"]["category"], "beverage")

    def test_barcode_route_propagates_scoring_result(self):
        off = {
            "found": True,
            "barcode": "1234567890123",
            "product_name": "Sample",
            "nutrition_per_100g": {
                key: {"value": value, "unit": "mg" if key == "sodium" else "g"}
                for key, value in COMPLETE_NUTRITION.items()
            },
            "ingredients_text": "flour, E500",
            "additives_tags": ["en:e500"],
            "additives_available": True,
            "nova_group": 4,
            "nova_source": "open_food_facts",
        }

        async def request():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.get("/api/v1/open-food-facts/1234567890123")

        with patch("main.fetch_open_food_facts_product", new=AsyncMock(return_value=off)):
            response = asyncio.run(request())

        self.assertEqual(response.status_code, 200)
        self.assertIn("scoring", response.json())
        self.assertIn("scores", response.json()["scoring"])

    def test_ocr_route_propagates_scoring_result(self):
        ocr_text = (
            "Ingredients: flour, E500\n"
            "Nutrition information per 100 g\n"
            "Calories 431 kcal\nTotal fat 14.6 g\nSaturated fat 8.2 g\n"
            "Sodium 414 mg\nTotal sugars 18.8 g\nDietary fiber 1.6 g\nProtein 20.5 g"
        )

        async def request():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.post(
                    "/api/v1/ocr",
                    files={"file": ("label.png", b"image-bytes", "image/png")},
                )

        with patch("main.extract_text_from_image", return_value={
            "job_id": "ocr-job-score", "status": "completed", "text": ocr_text,
        }):
            response = asyncio.run(request())

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("scoring", body)
        self.assertIn("scores", body["product_analysis"]["scoring"])


if __name__ == "__main__":
    unittest.main()
