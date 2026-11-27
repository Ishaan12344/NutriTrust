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
    def request_analysis(self, *, barcode=None, text=LABEL_TEXT, ingredients_text=None, off_result=None, off_error=None):
        async def request():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                files = {"file": ("label.png", b"image-bytes", "image/png")}
                if ingredients_text is not None:
                    files["ingredients_file"] = (
                        "ingredients.png", b"ingredients-bytes", "image/png",
                    )
                params = {"barcode": barcode} if barcode is not None else None
                return await client.post("/api/v1/ocr", files=files, params=params)

        def fake_ocr(_image_bytes, filename, _content_type):
            if filename == "ingredients.png":
                return {
                    "job_id": "ocr-job-2", "status": "completed", "text": ingredients_text,
                }
            return {
                "job_id": "ocr-job-1", "status": "completed", "text": text,
            }

        async def fetch_off(_barcode):
            if off_error:
                raise off_error
            return off_result

        with patch("main.extract_text_from_image", side_effect=fake_ocr), patch("main.fetch_open_food_facts_product", new=AsyncMock(side_effect=fetch_off)) as fetch:
            response = asyncio.run(request())
        return response, fetch

    def test_dual_image_merges_ingredients_and_label_additives(self):
        response, _ = self.request_analysis(
            text=(
                "Product Name: Sample Bar\n"
                "Nutrition information per 100 g\n"
                "Total Fat | 5 g\nProtein | 4 g"
            ),
            ingredients_text=(
                "Ingredients: oats, sugar, cocoa, raising agent (500)\n"
                "Contains: milk\nMay contain traces of soy"
            ),
        )
        analysis = response.json()["product_analysis"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(analysis["ingredients"]["text"], "oats, sugar, cocoa, raising agent (500)")
        self.assertEqual(analysis["allergens"]["declaration"], "milk")
        self.assertEqual(analysis["classification"]["additives_tags"], ["E500"])
        self.assertEqual(analysis["classification"]["additives_count"], 1)
        self.assertEqual(analysis["data_sources"]["additives"], "ocr_label")
        self.assertEqual(analysis["ocr"]["ingredients_status"], "completed")
        self.assertEqual(
            analysis["scoring"]["scores"]["additive_safety"]["status"], "known"
        )

    def test_dual_image_end_to_end_calculations_and_findings_agree(self):
        response, _ = self.request_analysis(
            text=(
                "Product Name: Masala Noodles\n"
                "Nutrition information per 100 g\n"
                "Energy | 450 kcal\nTotal Fat | 20 g\nSaturated Fat | 10 g\n"
                "Total Sugars | 25 g\nProtein | 8 g\nSalt | 1.5 g"
            ),
            ingredients_text=(
                "INGREDIENTS: Wheat flour, sugar, edible vegetable oil, "
                "raising agents (503(ii), 500(ii)), sodium benzoate, "
                "antioxidant (319)\nContains: wheat"
            ),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        analysis = body["product_analysis"]

        # Every additive in the OCR ingredient list is identified.
        self.assertEqual(
            analysis["classification"]["additives_tags"],
            ["E211", "E319", "E500", "E503"],
        )

        # NOVA and Nutri-Score are calculated internally without Open Food Facts.
        self.assertEqual(analysis["open_food_facts"]["request_status"], "not_requested")
        self.assertEqual(body["nova"]["status"], "classified")
        self.assertIn(body["nova"]["group"], (1, 2, 3, 4))
        self.assertIn(
            body["nutri_score"]["status"],
            {"calculated", "calculated_with_assumptions"},
        )
        self.assertIn(body["nutri_score"]["grade"], {"A", "B", "C", "D", "E"})

        # Internal health analysis remains consistent with the engine results.
        findings = {f["id"]: f for f in analysis["health_analysis"]["findings"]}
        self.assertEqual(findings["classification.nova_group"]["status"], "known")
        self.assertEqual(findings["classification.nova_group"]["measured"], body["nova"]["group"])
        self.assertEqual(
            findings["classification.nutriscore_grade"]["measured"], body["nutri_score"]["grade"]
        )
        identifiers = {
            item["identifier"]
            for item in findings["ingredients.identified_additives"]["measured"]
        }
        self.assertEqual(identifiers, {"E211", "E319", "E500", "E503"})

        warnings = analysis["health_analysis"]["warnings"]
        self.assertFalse(any("NOVA group was not supplied" in w for w in warnings))
        self.assertFalse(any("Nutri-Score grade was not supplied" in w for w in warnings))
        self.assertFalse(any("Additive identification" in w for w in warnings))

    def test_failed_ingredients_ocr_does_not_fail_the_scan(self):
        async def request():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.post(
                    "/api/v1/ocr",
                    files={
                        "file": ("label.png", b"image-bytes", "image/png"),
                        "ingredients_file": ("ingredients.png", b"bad-bytes", "image/png"),
                    },
                )

        def fake_ocr(_image_bytes, filename, _content_type):
            if filename == "ingredients.png":
                raise RuntimeError("No readable text was detected. Try a clearer image.")
            return {"job_id": "ocr-job-1", "status": "completed", "text": LABEL_TEXT}

        with patch("main.extract_text_from_image", side_effect=fake_ocr), patch("main.save_scan_and_product"):
            response = asyncio.run(request())

        self.assertEqual(response.status_code, 200)
        analysis = response.json()["product_analysis"]
        self.assertEqual(analysis["ocr"]["ingredients_status"], "failed")
        self.assertEqual(analysis["ingredients"]["source"], "ocr_label")
        self.assertTrue(any("ingredients photo" in w.lower() for w in analysis["warnings"]))

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
        analysis = response.json()["product_analysis"]
        self.assertEqual(analysis["product"]["name"], "Database Product")
        self.assertEqual(analysis["identification"]["requested_barcode"], barcode)
        self.assertNotIn("data_quality", analysis)
        self.assertIn("scoring", analysis)
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
            "product_name": "Sample Bar",
            "nutrition_per_100g": {"total_fat": {"value": 9.0, "unit": "g"}},
        }
        response, _ = self.request_analysis(barcode="1234567890123", off_result=off)
        analysis = response.json()["product_analysis"]
        self.assertEqual(analysis["nutrition"]["per_100g"]["total_fat"]["value"], 5.0)
        self.assertEqual(analysis["nutrition"]["per_100g"]["total_fat"]["source"], "ocr_label")
        conflict = analysis["conflicts"][0]
        self.assertEqual(conflict["selected_source"], "ocr_label")
        self.assertEqual(conflict["open_food_facts_value"], 9.0)

    def test_off_is_not_merged_when_label_identity_cannot_be_verified(self):
        off = {
            "found": True,
            "barcode": "1234567890123",
            "nutrition_per_100g": {"total_fat": {"value": 9.0, "unit": "g"}},
        }
        response, _ = self.request_analysis(barcode="1234567890123", off_result=off)
        analysis = response.json()["product_analysis"]
        self.assertEqual(analysis["open_food_facts"]["identity_match_status"], "barcode_supplied_unverified")
        self.assertFalse(analysis["open_food_facts"]["used_for_merge"])
        self.assertEqual(analysis["nutrition"]["per_100g"]["total_fat"]["value"], 5.0)

    def test_missing_data_remains_missing_and_allergen_status_is_unknown(self):
        response, _ = self.request_analysis(text="Product wrapper text only")
        analysis = response.json()["product_analysis"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(analysis["nutrition"]["per_100g"], {})
        self.assertEqual(analysis["ingredients"]["text"], None)
        self.assertEqual(analysis["allergens"]["declaration"], None)
        self.assertEqual(analysis["allergens"]["status"], "unknown")
        self.assertNotIn("missing_data_warnings", analysis)
        self.assertIsNone(analysis["ingredients"]["text"])

    def test_sarvam_markdown_ocr_populates_macros_and_nutritrust_score(self):
        sarvam_md = (
            "Product Name: Choco Biscuits\n"
            "Ingredients: Refined wheat flour, sugar, palm oil, cocoa solids, raising agent (500(ii))\n"
            "Nutrition Information\n"
            "Serving size: 20 g\n"
            "| Nutrient | Per serving | Per 100 gm |\n"
            "| --- | --- | --- |\n"
            "| Energy (kcal) | 96 | 480 |\n"
            "| Fat | 4 gm | 20 gm |\n"
            "| Saturates | 2 gm | 10 gm |\n"
            "| Carbohydrate | 13 gm | 65 gm |\n"
            "| Total Sugars | | |\n"
            "24 gm\n"
            "| Protein | 1.4 gm | 7 gm |\n"
            "| Sodium | 60 mg | 300 mg |\n"
        )
        response, _ = self.request_analysis(text=sarvam_md)
        self.assertEqual(response.status_code, 200)
        analysis = response.json()["product_analysis"]
        self.assertEqual(analysis["nutrition"]["per_100g"]["sugar"]["value"], 24.0)
        self.assertEqual(analysis["nutrition"]["per_100g"]["protein"]["value"], 7.0)
        self.assertIsInstance(analysis["scoring"]["scores"]["overall"], int)
        self.assertEqual(
            analysis["scoring"]["scores"]["nova_processing"]["source"],
            "nutritrust_nova_engine",
        )


if __name__ == "__main__":
    unittest.main()
