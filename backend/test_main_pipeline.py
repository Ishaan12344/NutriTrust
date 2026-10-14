import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from main import app


LABEL_TEXT = (
    "Product Name: Sample Bar\n"
    "Ingredients: oats, sugar, cocoa\n"
    "Contains: milk\n"
    "Nutrition information per 100 g\n"
    "Total Fat | 5 g\nProtein | 4 g"
)


class ProductAnalysisPipelineTests(unittest.TestCase):
    def request_analysis(self, *, barcode=None, text=LABEL_TEXT, off_result=None, off_error=None):
        async def request():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                files = {"file": ("label.png", b"image-bytes", "image/png")}
                params = {"barcode": barcode} if barcode is not None else None
                return await client.post("/api/v1/ocr", files=files, params=params)

        async def fetch_off(_barcode):
            if off_error:
                raise off_error
            return off_result

        with patch("main.extract_text_from_image", return_value={
            "job_id": "ocr-job-1", "status": "completed", "text": text,
        }), patch("main.fetch_open_food_facts_product", new=AsyncMock(side_effect=fetch_off)) as fetch:
            response = asyncio.run(request())
        return response, fetch

    def test_ocr_only_analysis_has_unified_response(self):
        response, fetch = self.request_analysis()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        analysis = body["product_analysis"]
        self.assertIsNone(body["health_analysis"]["overall_score"])
        self.assertIn("findings", analysis["health_analysis"])
        self.assertEqual(analysis["ocr"]["source"], "sarvam_ocr")
        self.assertEqual(analysis["identification"]["name"], "Sample Bar")
        self.assertEqual(analysis["data_sources"]["product_name"], "ocr_label")
        self.assertEqual(analysis["ingredients"]["source"], "ocr_label")
        self.assertEqual(analysis["allergens"]["declaration"], "milk")
        self.assertEqual(analysis["nutrition"]["per_100g"]["total_fat"]["value"], 5.0)
        self.assertEqual(analysis["open_food_facts"]["request_status"], "not_requested")
        self.assertFalse(analysis["open_food_facts"]["used_for_merge"])
        fetch.assert_not_awaited()

    def test_ocr_plus_matching_barcode_preserves_both_sources(self):
        off = {
            "found": True, "source": "open_food_facts", "barcode": "1234567890123",
            "product_name": "Sample Bar", "brands": "Example Brand",
            "ingredients_text": "database ingredients", "allergens_tags": ["en:milk"],
            "traces_tags": ["en:soy"], "nutrition_basis": "per_100g",
            "nutrition_source": "open_food_facts_v3.6", "nutrition_per_100g": {
                "total_fat": {"value": 7.0, "unit": "g"},
            }, "available_fields": ["product_name", "nutrition"],
        }
        response, fetch = self.request_analysis(barcode="1234567890123", off_result=off)
        analysis = response.json()["product_analysis"]
        self.assertEqual(response.status_code, 200)
        fetch.assert_awaited_once_with("1234567890123")
        self.assertEqual(analysis["identification"]["name"], "Sample Bar")
        self.assertEqual(analysis["data_sources"]["product_name"], "ocr_label")
        self.assertEqual(analysis["allergens"]["traces_tags"], ["en:soy"])
        self.assertEqual(analysis["open_food_facts"]["nutrition_source"], "open_food_facts_v3.6")
        self.assertEqual(analysis["open_food_facts"]["identity_match_status"], "matched_by_label")
        self.assertTrue(analysis["open_food_facts"]["used_for_merge"])

    def test_barcode_only_lookup_route(self):
        barcode = "1234567890123"
        off = {"found": True, "barcode": barcode, "product_name": "Database Product"}

        async def request():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.get(f"/api/v1/open-food-facts/{barcode}")

        with patch("main.fetch_open_food_facts_product", new=AsyncMock(return_value=off)) as fetch:
            response = asyncio.run(request())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], off)
        fetch.assert_awaited_once_with(barcode)

    def test_missing_off_product_preserves_ocr(self):
        response, _ = self.request_analysis(barcode="1234567890123", off_result={
            "found": False, "message": "No product record",
        })
        analysis = response.json()["product_analysis"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(analysis["ingredients"]["text"], "oats, sugar, cocoa")
        self.assertEqual(analysis["open_food_facts"]["request_status"], "not_found")
        self.assertFalse(analysis["open_food_facts"]["found"])
        self.assertFalse(analysis["open_food_facts"]["used_for_merge"])
        self.assertIn("No product record", analysis["warnings"])

    def test_conflicting_barcode_identity_is_retained_but_not_merged(self):
        off = {
            "found": True, "source": "open_food_facts", "barcode": "1234567890123",
            "product_name": "Nutella", "brands": "Ferrero",
            "nutrition_basis": "per_100g",
            "nutrition_per_100g": {"total_fat": {"value": 30.0, "unit": "g"}},
        }
        response, _ = self.request_analysis(barcode="1234567890123", off_result=off)
        body = response.json()
        analysis = body["product_analysis"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(analysis["open_food_facts"]["request_status"], "found")
        self.assertTrue(analysis["open_food_facts"]["found"])
        self.assertFalse(analysis["open_food_facts"]["used_for_merge"])
        self.assertEqual(analysis["open_food_facts"]["identity_match_status"], "identity_mismatch")
        self.assertEqual(analysis["nutrition"]["per_100g"]["total_fat"]["value"], 5.0)
        self.assertEqual(body["open_food_facts"]["product_name"], "Nutella")
        self.assertTrue(any("identity conflicts" in warning for warning in analysis["warnings"]))

    def test_invalid_optional_barcode_keeps_ocr_analysis(self):
        response, fetch = self.request_analysis(barcode="not-a-barcode", off_error=ValueError("Barcode must contain digits only."))
        analysis = response.json()["product_analysis"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(analysis["open_food_facts"]["request_status"], "invalid_barcode")
        self.assertEqual(analysis["ingredients"]["source"], "ocr_label")
        fetch.assert_awaited_once_with("not-a-barcode")

    def test_external_api_failure_preserves_ocr_and_warns(self):
        request = httpx.Request("GET", "https://world.openfoodfacts.org")
        response, _ = self.request_analysis(
            barcode="1234567890123", off_error=httpx.ConnectError("offline", request=request),
        )
        analysis = response.json()["product_analysis"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(analysis["open_food_facts"]["request_status"], "failed")
        self.assertEqual(analysis["ingredients"]["source"], "ocr_label")
        self.assertTrue(any("could not be reached" in warning for warning in analysis["warnings"]))

    def test_ocr_wins_conflict_and_off_alternative_is_retained(self):
        off = {
            "found": True, "barcode": "1234567890123", "nutrition_basis": "per_100g",
            "nutrition_per_100g": {"total_fat": {"value": 9.0, "unit": "g"}},
        }
        response, _ = self.request_analysis(barcode="1234567890123", off_result=off)
        analysis = response.json()["product_analysis"]
        self.assertEqual(analysis["nutrition"]["per_100g"]["total_fat"]["value"], 5.0)
        self.assertEqual(analysis["nutrition"]["per_100g"]["total_fat"]["source"], "ocr_label")
        conflict = analysis["conflicts"][0]
        self.assertEqual(conflict["selected_source"], "ocr_label")
        self.assertEqual(conflict["open_food_facts_value"], 9.0)

    def test_missing_data_remains_missing_and_allergen_status_is_unknown(self):
        response, _ = self.request_analysis(text="Product wrapper text only")
        analysis = response.json()["product_analysis"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(analysis["nutrition"]["per_100g"], {})
        self.assertEqual(analysis["ingredients"]["text"], None)
        self.assertEqual(analysis["allergens"]["declaration"], None)
        self.assertEqual(analysis["allergens"]["status"], "unknown")
        self.assertTrue(any("does not mean" in warning for warning in analysis["missing_data_warnings"]))
        self.assertIsNone(analysis["ingredients"]["text"])


if __name__ == "__main__":
    unittest.main()
