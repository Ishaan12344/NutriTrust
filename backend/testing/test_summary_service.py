"""Tests for the optional local-LLM summary (no model weights are loaded)."""

import asyncio
import time
import unittest
from unittest import mock

import httpx

from summary_service import (
    _run_with_timeout,
    allergy_check,
    allergy_results,
    build_messages,
    data_sufficiency,
    fallback_summary,
    product_context,
    profile_context,
    summarize_analysis,
)


PROFILE = {
    "name": "Asha",
    "age": 45,
    "weight": 68.0,
    "gender": "female",
    "allergies": ["Peanuts"],
    "allergy_other": "shellfish",
    "conditions": ["Diabetes"],
    "condition_other": None,
    "preferences": ["Vegan"],
}

ANALYSIS = {
    "product": {"name": "Oat Crunch Bar", "brands": "Acme Foods", "categories": "snacks"},
    "nutrition": {
        "per_100g": {
            "energy_kcal": {"value": 420, "unit": "kcal", "basis": "per_100g"},
            "sugar": {"value": 28.0, "unit": "g", "basis": "per_100g"},
            "sodium": {"value": 310.0, "unit": "mg", "basis": "per_100g"},
            "fiber": {"value": 6.0, "unit": "g", "basis": "per_100g"},
        }
    },
    "ingredients": {"text": "Oats, cane sugar, palm oil, salt, natural flavouring"},
    "allergens": {
        "declaration": "May contain peanuts and milk.",
        "declared": ["peanuts"],
        "precautionary_traces": {"text": "May contain traces of nuts."},
    },
    "classification": {"nova_group": 4, "additives_tags": ["en:e322"]},
    "scoring": {"scores": {"overall": 34, "grade": "D", "grade_label": "Below average"}},
    "health_analysis": {
        "findings": [
            {
                "id": "nutrition.sugar",
                "severity": "attention",
                "explanation": "28 g/100 g is above the rule's high threshold.",
            },
            {
                "id": "nutrition.fiber",
                "severity": "informational",
                "explanation": "6 g/100 g is a known value.",
            },
        ]
    },
    "missing_data_warnings": ["Ingredient list is unavailable or unreadable."],
}


class ProfileContextTests(unittest.TestCase):
    def test_profile_lines_include_only_health_fields(self):
        lines = profile_context(PROFILE)
        text = "\n".join(lines)
        self.assertIn("Allergies: Peanuts, shellfish", text)
        self.assertIn("Health conditions: Diabetes", text)
        self.assertIn("Dietary preferences: Vegan", text)
        # Personal details are intentionally kept out of the prompt.
        self.assertNotIn("Asha", text)
        self.assertNotIn("45", text)
        self.assertNotIn("68", text)

    def test_empty_profile_is_safe(self):
        self.assertEqual(profile_context(None), [])
        self.assertEqual(profile_context({}), [])


class AllergyCheckTests(unittest.TestCase):
    def test_matches_and_non_matches_are_reported(self):
        lines = "\n".join(allergy_check(PROFILE, ANALYSIS))
        self.assertIn("matches the Peanuts allergy", lines)
        self.assertIn("not proof it is absent", lines)
        self.assertIn("shellfish", lines)

    def test_unavailable_label_text_is_stated(self):
        lines = allergy_check(PROFILE, {"product": {"name": "Bar"}})
        self.assertTrue(any("unavailable" in line for line in lines))

    def test_no_allergies_returns_nothing(self):
        self.assertEqual(allergy_check({"allergies": []}, ANALYSIS), [])

    def test_results_expose_match_state_and_data_availability(self):
        results = {
            allergy: (match, available)
            for allergy, match, available in allergy_results(PROFILE, ANALYSIS)
        }
        self.assertIsNotNone(results["Peanuts"][0])   # matched in the label text
        self.assertTrue(results["Peanuts"][1])        # and data was present
        self.assertIsNone(results["shellfish"][0])    # never mentioned
        # With no ingredient or allergen text the check cannot run at all.
        no_data = allergy_results(PROFILE, {"product": {"name": "Cheetos"}})
        self.assertTrue(no_data)
        self.assertFalse(any(available for _, _, available in no_data))


class FallbackSummaryTests(unittest.TestCase):
    def test_states_what_is_unknown_without_inventing_a_finding(self):
        text = fallback_summary(PROFILE, {"product": {"name": "Cheetos"}})
        self.assertIn("Cheetos", text)
        self.assertIn("could not be scored", text)
        self.assertIn("could not be checked", text)

    def test_uses_the_score_and_top_finding_when_present(self):
        text = fallback_summary(PROFILE, ANALYSIS)
        self.assertIn("34/100", text)
        self.assertIn("above the rule's high threshold", text)


class ProductContextTests(unittest.TestCase):
    def test_product_lines_carry_facts_and_skip_informational_findings(self):
        text = "\n".join(product_context(ANALYSIS))
        self.assertIn("Product: Oat Crunch Bar", text)
        self.assertIn("sugar 28 g", text)
        self.assertIn("NutriTrust score: 34/100", text)
        self.assertIn("nutrition.sugar", text)
        self.assertNotIn("nutrition.fiber", text)
        self.assertIn("Missing or unreadable data", text)

    def test_messages_include_profile_and_product(self):
        messages = build_messages(PROFILE, ANALYSIS)
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("never", messages[0]["content"].lower())
        self.assertIn("Diabetes", messages[1]["content"])
        self.assertIn("Oat Crunch Bar", messages[1]["content"])
        self.assertIn("Allergy check for this person", messages[1]["content"])


class SummarizeAnalysisTests(unittest.TestCase):
    def test_summary_is_returned_and_normalized(self):
        captured = {}

        def fake_generate(messages, max_new_tokens):
            captured["messages"] = messages
            captured["max_new_tokens"] = max_new_tokens
            return "  This   oat bar is high in sugar.  Check the label.  "

        result = summarize_analysis(
            PROFILE, ANALYSIS, generate=fake_generate, max_new_tokens=64
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["summary"], "This oat bar is high in sugar. Check the label.")
        self.assertEqual(captured["max_new_tokens"], 64)
        self.assertEqual(captured["messages"][0]["role"], "system")

    def test_generation_error_falls_back_to_a_deterministic_summary(self):
        def broken(messages, max_new_tokens):
            raise RuntimeError("boom")

        result = summarize_analysis(
            PROFILE, ANALYSIS, generate=broken, max_new_tokens=64
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["source"], "fallback")
        self.assertIsNone(result["model"])
        self.assertIn("boom", result["reason"])
        self.assertTrue(result["summary"])

    def test_timeout_falls_back_to_a_deterministic_summary(self):
        def slow(messages, max_new_tokens):
            raise TimeoutError("too slow")

        result = summarize_analysis(
            PROFILE, ANALYSIS, generate=slow, max_new_tokens=64
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["source"], "fallback")
        self.assertIn("too slow", result["reason"])

    def test_empty_output_falls_back_to_a_deterministic_summary(self):
        result = summarize_analysis(
            PROFILE, ANALYSIS, generate=lambda *_: "   ", max_new_tokens=8
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["source"], "fallback")
        self.assertIn("empty", result["reason"])

    def test_missing_analysis_is_insufficient_data(self):
        result = summarize_analysis(
            PROFILE, {}, generate=lambda *_: "ignored", max_new_tokens=8
        )
        self.assertEqual(result["status"], "insufficient_data")
        self.assertIsNone(result["summary"])

    def test_no_product_data_skips_the_model_entirely(self):
        name_only = {"product": {"name": "Cheetos", "brands": "Frito-Lay"}}

        def must_not_run(messages, max_new_tokens):
            raise AssertionError("the model must not be called without product facts")

        result = summarize_analysis(
            PROFILE, name_only, generate=must_not_run, max_new_tokens=64
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["source"], "fallback")
        self.assertIn("Cheetos", result["summary"])
        self.assertIn("could not be scored", result["summary"])
        # The unavailable allergy check must survive into the fallback text.
        self.assertIn("could not be checked", result["summary"])


class GroundingTests(unittest.TestCase):
    """The model must not claim things the pipeline's facts do not support."""

    # Nutrition is present so these analyses reach the model, but there is no
    # ingredient or allergen data, which is the dangerous combination.
    NUTRITION_ONLY = {
        "product": {"name": "Cheetos"},
        "nutrition": {"per_100g": {"energy_kcal": {"value": 536, "unit": "kcal"}}},
        "scoring": {"scores": {"overall": 12, "grade": "E"}},
    }

    def _run(self, text, analysis=None):
        analysis = analysis if analysis is not None else self.NUTRITION_ONLY
        return summarize_analysis(
            PROFILE, analysis, generate=lambda *_: text, max_new_tokens=64
        )

    def test_invented_allergen_presence_is_rejected(self):
        result = self._run(
            "The allergy check indicates that the product contains peanuts, so take care."
        )
        self.assertEqual(result["source"], "fallback")
        self.assertIn("rejected", result["reason"])

    def test_allergen_free_claim_is_rejected(self):
        result = self._run("This product is allergen-free, so you can enjoy it.")
        self.assertEqual(result["source"], "fallback")
        self.assertIn("allergen-free", result["reason"])

    def test_band_for_an_unmeasured_nutrient_is_rejected(self):
        result = self._run("The product has high sugar, which matters for diabetes.")
        self.assertEqual(result["source"], "fallback")
        self.assertIn("sugar", result["reason"])

    def test_supported_summary_is_kept(self):
        result = self._run("This product is high in energy at 536 kcal per 100 g.")
        self.assertEqual(result["source"], "model")
        self.assertEqual(result["status"], "ok")

    def test_absence_claim_on_a_match_is_rejected(self):
        analysis = {
            "product": {"name": "Peanut bar"},
            "nutrition": {"per_100g": {"energy_kcal": {"value": 500, "unit": "kcal"}}},
            "allergens": {"declared": ["peanuts"]},
        }
        result = summarize_analysis(
            PROFILE,
            analysis,
            generate=lambda *_: "This product does not contain peanuts.",
            max_new_tokens=64,
        )
        self.assertEqual(result["source"], "fallback")
        self.assertIn("rejected", result["reason"])


class DataSufficiencyTests(unittest.TestCase):
    def test_nothing_to_reason_from_is_detected(self):
        self.assertEqual(data_sufficiency({"product": {"name": "Cheetos"}}), "none")
        self.assertEqual(data_sufficiency({}), "none")

    def test_partial_nutrition_is_enough_to_use_the_model(self):
        analysis = {
            "product": {"name": "Cheetos"},
            "nutrition": {"per_100g": {"energy_kcal": {"value": 536, "unit": "kcal"}}},
        }
        self.assertEqual(data_sufficiency(analysis), "some")

    def test_ingredients_alone_are_enough(self):
        analysis = {"ingredients": {"text": "Oats, sugar, salt"}}
        self.assertEqual(data_sufficiency(analysis), "some")

    def test_analysis_without_analysis_is_insufficient(self):
        result = summarize_analysis(
            PROFILE, None, generate=lambda *_: "ignored", max_new_tokens=8
        )
        self.assertEqual(result["status"], "insufficient_data")

    def test_run_with_timeout_raises(self):
        with self.assertRaises(TimeoutError):
            _run_with_timeout(lambda: time.sleep(0.2), 0.01)


class SummaryRouteTests(unittest.TestCase):
    @staticmethod
    def request(method: str, path: str, **kwargs):
        from main import app

        async def send():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(send())

    def test_route_is_documented(self):
        response = self.request("GET", "/openapi.json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("/api/v1/summary", response.json()["paths"])

    def test_missing_analysis_is_rejected(self):
        response = self.request("POST", "/api/v1/summary", json={"username": "asha"})
        self.assertEqual(response.status_code, 422)

    def test_route_returns_summary_without_touching_the_model(self):
        fake_result = {
            "status": "ok",
            "summary": "A short summary.",
            "model": "Qwen2.5-1.5B-Instruct",
            "prompt_version": "1.0",
        }
        with mock.patch("main._summarize_analysis", return_value=fake_result) as patched:
            response = self.request(
                "POST", "/api/v1/summary", json={"product_analysis": ANALYSIS}
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["summary"], "A short summary.")
        self.assertEqual(patched.call_args.args[0], {})
        self.assertEqual(patched.call_args.args[1], ANALYSIS)


if __name__ == "__main__":
    unittest.main()
