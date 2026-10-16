import unittest

from health_analyzer import analyze_product_health


def product(per_100g=None, *, per_serving=None, conflicts=None, categories="Food products",
            ingredients=None, allergens=None, classification=None, data_sources=None,
            off_found=False):
    per_100g = per_100g or {}
    per_serving = per_serving or {}
    ingredients = ingredients if ingredients is not None else {"text": "", "items": [], "source": None}
    allergens = allergens if allergens is not None else {
        "declared": [], "declaration": None,
        "precautionary_traces": {"allergens": [], "text": None},
        "open_food_facts_tags": [],
    }
    return {
        "product": {"categories": categories},
        "nutrition": {"per_100g": per_100g, "per_serving": per_serving, "conflicts": conflicts or []},
        "ingredients": ingredients,
        "allergens": allergens,
        "classification": classification or {},
        "data_sources": data_sources or {},
        "open_food_facts": {"found": off_found},
    }


def nutrient(value, unit, source="ocr_label"):
    return {"value": value, "unit": unit, "source": source}


class HealthAnalyzerTests(unittest.TestCase):
    @staticmethod
    def finding(result, finding_id):
        return next(item for item in result["findings"] if item["id"] == finding_id)

    def test_sugar_threshold_boundaries(self):
        for value, category in [(5, "low"), (5.01, "medium"), (22.5, "medium"), (22.5001, "high")]:
            with self.subTest(value=value):
                result = analyze_product_health(product({"sugar": nutrient(value, "g")}))
                finding = self.finding(result, "nutrition.sugar")
                self.assertEqual(finding["category"], category)
                self.assertEqual(finding["measured"]["basis"], "per_100g")

    def test_saturated_fat_and_total_fat_boundaries(self):
        for key, unit, values in [
            ("saturated_fat", "g", [(1.5, "low"), (1.51, "medium"), (5, "medium"), (5.01, "high")]),
            ("total_fat", "g", [(3, "low"), (3.01, "medium"), (17.5, "medium"), (17.51, "high")]),
        ]:
            for value, category in values:
                with self.subTest(nutrient=key, value=value):
                    result = analyze_product_health(product({key: nutrient(value, unit)}))
                    self.assertEqual(self.finding(result, f"nutrition.{key}")["category"], category)

    def test_sodium_thresholds_convert_sodium_to_salt_equivalent(self):
        for value, category in [(120, "low"), (120.01, "medium"), (600, "medium"), (600.01, "high")]:
            with self.subTest(value=value):
                result = analyze_product_health(product({"sodium": nutrient(value, "mg")}))
                finding = self.finding(result, "nutrition.sodium")
                self.assertEqual(finding["category"], category)
                self.assertIn("sodium × 2.5", finding["applicable_rule"]["conversion"])

    def test_per_serving_values_are_reported_without_per_100g_band(self):
        result = analyze_product_health(product(per_serving={"sugar": nutrient(12, "g")}))
        finding = self.finding(result, "nutrition.sugar")
        self.assertEqual(finding["status"], "known")
        self.assertEqual(finding["category"], "reported_value")
        self.assertEqual(finding["measured"]["basis"], "per_serving")
        self.assertTrue(any("per serving" in warning for warning in result["warnings"]))

    def test_missing_invalid_and_conflicting_values_are_distinguished(self):
        absent = analyze_product_health(product())
        self.assertEqual(self.finding(absent, "nutrition.sugar")["status"], "missing")

        invalid = analyze_product_health(product({"sugar": nutrient(float("nan"), "g")}))
        self.assertEqual(self.finding(invalid, "nutrition.sugar")["status"], "invalid")

        conflict = analyze_product_health(product(
            {"sugar": nutrient(8, "g")},
            conflicts=[{
                "nutrient": "sugar", "ocr_value": 8, "open_food_facts_value": 12,
                "selected_source": "ocr_label", "alternative_source": "open_food_facts",
            }],
        ))
        finding = self.finding(conflict, "nutrition.sugar")
        self.assertEqual(finding["status"], "conflicting")
        self.assertEqual(finding["conflict"]["open_food_facts_value"], 12)
        self.assertIsNone(conflict["overall_score"])

    def test_ocr_extraction_review_rows_surface_as_uncertain_findings(self):
        candidate = product({"total_fat": nutrient(14.87, "g")})
        candidate["nutrition"]["ocr_normalization"] = {
            "nutrition_review": [
                {"status": "invalid", "nutrient": "protein", "value": 0.0,
                 "unit": "mcg", "row": "Protein 0.00 mcg",
                 "reason": "Unit mcg is incompatible with protein."},
                {"status": "unresolved", "row": "20.71 g",
                 "reason": "A quantity lacks a nutrient label."},
            ]
        }
        result = analyze_product_health(candidate)
        review_findings = [f for f in result["findings"] if f["type"] == "nutrition_extraction_review"]
        self.assertEqual([f["status"] for f in review_findings], ["invalid", "unresolved"])
        self.assertTrue(result["needs_review"])
        self.assertIsNone(result["overall_score"])

    def test_fiber_and_protein_are_observations_without_unvalidated_thresholds(self):
        result = analyze_product_health(product({
            "fiber": nutrient(4, "g"), "protein": nutrient(7, "g"),
        }))
        self.assertEqual(self.finding(result, "nutrition.fiber")["category"], "reported_value")
        self.assertIsNone(self.finding(result, "nutrition.protein")["applicable_rule"])

    def test_ingredients_keep_source_order_and_no_proportions_are_inferred(self):
        result = analyze_product_health(product(ingredients={
            "text": "oats, sugar, cocoa", "items": ["oats", "sugar", "cocoa"], "source": "ocr_label",
        }))
        finding = self.finding(result, "ingredients.composition_and_order")
        self.assertEqual(finding["measured"]["ordered_items"], ["oats", "sugar", "cocoa"])
        self.assertIn("no ingredient proportions", finding["explanation"])

    def test_allergen_declaration_and_precautionary_traces_stay_separate(self):
        result = analyze_product_health(product(allergens={
            "declared": ["milk"], "declaration": "Contains milk",
            "precautionary_traces": {"allergens": ["soy"], "text": "May contain soy"},
            "open_food_facts_tags": ["en:milk"],
        }))
        self.assertEqual(self.finding(result, "allergens.label_declaration")["measured"]["declared"], ["milk"])
        self.assertEqual(self.finding(result, "allergens.precautionary_traces")["measured"]["may_contain"], ["soy"])
        self.assertEqual(self.finding(result, "allergens.open_food_facts_tags")["category"], "database_observation")

    def test_missing_allergen_data_is_not_interpreted_as_allergen_free(self):
        result = analyze_product_health(product())
        declaration = self.finding(result, "allergens.label_declaration")
        self.assertEqual(declaration["status"], "missing")
        self.assertIn("does not mean allergen-free", declaration["explanation"])

    def test_additive_presence_is_not_called_dangerous(self):
        result = analyze_product_health(product(
            ingredients={"text": "oats, E322", "items": ["oats", "E 322"], "source": "ocr_label"},
        ))
        finding = self.finding(result, "ingredients.identified_additives")
        self.assertEqual(finding["measured"][0]["identifier"], "E322")
        self.assertIn("not evidence", finding["explanation"])
        self.assertEqual(finding["severity"], "informational")

    def test_nova_and_nutriscore_require_valid_off_provenance(self):
        trusted = analyze_product_health(product(
            classification={"nova_group": 4, "nutriscore_grade": "c"},
            data_sources={"nova_group": "open_food_facts", "nutriscore_grade": "open_food_facts"},
            off_found=True,
        ))
        self.assertEqual(self.finding(trusted, "classification.nova_group")["status"], "known")
        self.assertEqual(self.finding(trusted, "classification.nutriscore_grade")["measured"], "c")

        untrusted = analyze_product_health(product(
            classification={"nova_group": 5}, data_sources={"nova_group": "ocr_label"}, off_found=True,
        ))
        self.assertEqual(self.finding(untrusted, "classification.nova_group")["status"], "invalid")

    def test_beverages_are_not_assessed_with_food_per_100g_bands(self):
        result = analyze_product_health(product(
            {"sugar": nutrient(12, "g")}, categories="Beverages and soft drinks",
        ))
        finding = self.finding(result, "nutrition.sugar")
        self.assertEqual(finding["status"], "known")
        self.assertEqual(finding["category"], "not_assessed_product_basis")
        self.assertIsNone(finding["applicable_rule"])

    def test_incomplete_product_has_no_overall_score_and_warnings(self):
        result = analyze_product_health(None)
        self.assertIsNone(result["overall_score"])
        self.assertEqual(result["overall_score_status"], "not_calculated")
        self.assertTrue(result["warnings"])
        self.assertTrue(any(finding["status"] == "missing" for finding in result["findings"]))


if __name__ == "__main__":
    unittest.main()
