"""End-to-end coverage for the three engines in the FastAPI workflow."""

import asyncio
import unittest
from unittest.mock import patch

import httpx

from main import app


def request(method: str, path: str, **kwargs):
    async def send():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send())


class FoodIntelligenceIntegrationTests(unittest.TestCase):
    def test_ocr_response_exposes_engines_without_breaking_existing_scoring(self):
        text = (
            "Product Name: Sample Bar\n"
            "Ingredients: oats, sugar, cocoa\n"
            "Nutrition information per 100 g\n"
            "Total Fat | 5 g\nProtein | 4 g"
        )

        def fake_ocr(_image_bytes, filename, _content_type):
            return {"job_id": "ocr-food-intel", "status": "completed", "text": text}

        with patch("main.extract_text_from_image", side_effect=fake_ocr), patch(
            "main.save_scan_and_product"
        ):
            response = request(
                "POST",
                "/api/v1/ocr",
                files={"file": ("label.png", b"image-bytes", "image/png")},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        analysis = body["product_analysis"]
        self.assertEqual(body["nutri_score"]["status"], "incomplete_data")
        self.assertIsNone(body["nutri_score"]["grade"])
        self.assertIn("nova", analysis)
        self.assertIn("additive_regulatory", analysis)
        self.assertNotIn("data_quality", analysis)
        self.assertIn("scoring", analysis)
        self.assertEqual(
            analysis["classification"]["nutriscore"]["algorithm_version"],
            "updated_2023",
        )

    def test_manual_endpoint_calculates_all_three_assessments(self):
        payload = {
            "product_name": "Wholegrain bread-like product",
            "category": "Condensed milk products",
            "ingredients_text": "flour, water, salt, carrageenan",
            "additives": ["E407"],
            "energy_kcal_per_100g": 900 / 4.184,
            "sugars_per_100g": 3,
            "saturated_fat_per_100g": 0.5,
            "salt_g_per_100g": 0.3,
            "fiber_per_100g": 6,
            "protein_per_100g": 10,
            "fruit_vegetable_percent": 0,
        }
        with patch("main.save_scan_and_product"):
            response = request("POST", "/api/v1/manual-assessment", json=payload)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        nutri = body["nutri_score"]
        self.assertEqual(nutri["status"], "calculated")
        self.assertEqual(nutri["score"], -4)
        self.assertEqual(nutri["grade"], "A")
        self.assertEqual(body["product_analysis"]["nutri_score"], nutri)
        additive = body["additive_regulatory"]
        self.assertEqual(additive["overall_status"], "permitted_with_conditions")
        self.assertEqual(additive["additives"][0]["max_level"]["value"], 150)
        self.assertEqual(additive["additives"][0]["name"], "Carrageenan")
        self.assertIn("thickener", additive["additives"][0]["functional_class"])
        self.assertIn(
            "Distinct from processed eucheuma seaweed INS 407a.",
            additive["additives"][0]["notes"],
        )
        self.assertEqual(additive["compliance_status"], "compliance_not_verified")
        self.assertIn(body["nova"]["status"], {"classified", "uncertain"})

    def test_manual_endpoint_returns_legacy_purpose_for_unverified_additive(self):
        payload = {
            "product_name": "Turmeric-colored product",
            "additives": ["E100"],
        }
        with patch("main.save_scan_and_product"):
            response = request("POST", "/api/v1/manual-assessment", json=payload)

        self.assertEqual(response.status_code, 200)
        additive = response.json()["additive_regulatory"]["additives"][0]
        self.assertEqual(additive["name"], "Curcumin")
        self.assertIn("yellow color", additive["purpose"])
        self.assertEqual(additive["permission_status"], "unable_to_verify")

    def test_ocr_response_keeps_additive_details_from_image_analysis(self):
        text = (
            "Product Name: Turmeric-colored product\n"
            "Ingredients: oats, sugar, E100\n"
            "Nutrition information per 100 g\nEnergy 200 kcal"
        )

        def fake_ocr(_image_bytes, filename, _content_type):
            return {"job_id": "ocr-additive", "status": "completed", "text": text}

        with patch("main.extract_text_from_image", side_effect=fake_ocr), patch(
            "main.save_scan_and_product"
        ):
            response = request(
                "POST",
                "/api/v1/ocr",
                files={"file": ("label.png", b"image-bytes", "image/png")},
            )

        self.assertEqual(response.status_code, 200)
        additive = response.json()["product_analysis"]["additive_regulatory"][
            "additives"
        ][0]
        self.assertEqual(additive["identified_as"], "E100")
        self.assertEqual(additive["name"], "Curcumin")
        self.assertEqual(additive["functional_class"], ["colour"])
        self.assertIn("yellow color", additive["purpose"])
        self.assertTrue(
            any(
                "Verify category-specific colour list" in condition
                for condition in additive["regulatory_notes"][0]["conditions"]
            )
        )
        self.assertEqual(additive["reference_risk"], "safe")
        self.assertEqual(additive["permission_status"], "unable_to_verify")

    def test_engine_failure_is_isolated_from_other_assessments(self):
        payload = {
            "product_name": "Test food",
            "energy_kcal_per_100g": 200,
            "sugars_per_100g": 2,
            "saturated_fat_per_100g": 1,
            "salt_g_per_100g": 0.2,
            "fibre_per_100g": 2,
            "protein_per_100g": 5,
        }
        with patch("main.save_scan_and_product"), patch(
            "analysis_pipeline.classify_nova", side_effect=RuntimeError("engine down")
        ):
            response = request("POST", "/api/v1/manual-assessment", json=payload)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["nova"]["status"], "engine_error")
        self.assertIn("engine down", body["nova"]["error"])
        self.assertIn("calculated", body["nutri_score"]["status"])
        self.assertIn(
            body["additive_regulatory"]["overall_status"],
            {
                "insufficient_information",
                "no_additives_identified",
            },
        )


if __name__ == "__main__":
    unittest.main()
