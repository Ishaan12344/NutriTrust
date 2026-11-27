import unittest
from nutrition_normalizer import normalize_nutrition
from nutrition_parser import parse_food_label


class NutritionNormalizerTests(unittest.TestCase):
    def base(self, raw_text, basis=None):
        return {
            "raw_text": raw_text,
            "serving_size": {"text": "30 g", "weight_g": 30},
            "servings_per_container": 4,
            "calories_per_serving_kcal": 150,
            "nutrition": {
                "total_fat": {"value": 6, "unit": "g"},
                "sodium": {"value": 120, "unit": "mg"},
                "dietary_fiber": {"value": 2, "unit": "g"},
            },
            "daily_values_percent": {"sodium": 5},
            "extraction": {"needs_review": False},
        }

    def test_per_serving_to_per_100g_and_package(self):
        result = normalize_nutrition(
            self.base("Nutrition Facts\nPer serving\nServing size 30 g")
        )
        self.assertEqual(result["reference_basis"]["detected"], "per_serving")
        self.assertEqual(result["per_serving"]["total_fat"], 6.0)
        self.assertEqual(result["per_100g"]["total_fat"], 20.0)
        self.assertEqual(result["per_100g"]["sodium"], 400.0)
        self.assertEqual(result["whole_package"]["energy_kcal"], 600.0)

    def test_per_100g_to_per_serving(self):
        parsed = self.base("Nutrition information per 100 g")
        parsed["nutrition"]["sodium"] = {"value": 0.4, "unit": "g"}
        result = normalize_nutrition(parsed)
        self.assertEqual(result["reference_basis"]["detected"], "per_100g")
        self.assertEqual(result["per_100g"]["sodium"], 400.0)
        self.assertEqual(result["per_serving"]["sodium"], 120.0)

    def test_unknown_basis_does_not_guess(self):
        result = normalize_nutrition(self.base("Nutrition Facts\nServing size 30 g"))
        self.assertEqual(result["reference_basis"]["detected"], "unknown")
        self.assertEqual(result["per_serving"], {})
        self.assertEqual(result["per_100g"], {})
        self.assertIn("total_fat", result["source_values"])
        self.assertTrue(result["needs_review"])

    def test_ambiguous_basis_does_not_convert(self):
        result = normalize_nutrition(self.base("Per 100 g\nPer serving"))
        self.assertEqual(result["reference_basis"]["detected"], "ambiguous")
        self.assertEqual(result["per_serving"], {})
        self.assertEqual(result["per_100g"], {})

    def test_unit_conversion(self):
        parsed = self.base("Per serving")
        parsed["nutrition"]["calcium"] = {"value": 250, "unit": "mg"}
        parsed["nutrition"]["protein"] = {"value": 5000, "unit": "mg"}
        result = normalize_nutrition(parsed, basis="per_serving")
        self.assertEqual(result["per_serving"]["protein"], 5.0)
        self.assertEqual(result["per_serving"]["calcium"], 250.0)

    def test_ocr_concatenated_serving_metadata_runs_through_normalizer(self):
        ocr_text = (
            "4 servings per containerServing size 1 Cup(227g)\n"
            "Amount per serving\nCalories 280\nTotal Fat | 10 g | 15%"
        )
        parsed = parse_food_label(ocr_text)
        result = normalize_nutrition(parsed)

        self.assertEqual(parsed["servings_per_container"], 4)
        self.assertEqual(parsed["serving_size"]["text"], "1 Cup(227g)")
        self.assertEqual(parsed["serving_size"]["weight_g"], 227.0)
        self.assertEqual(result["per_serving"]["total_fat"], 10.0)
        self.assertEqual(result["per_100g"]["total_fat"], 4.4053)
        self.assertEqual(result["whole_package"]["energy_kcal"], 1120.0)
        self.assertEqual(result["daily_values_percent"], {"total_fat": 15.0})
        self.assertEqual(result["serving_size"]["text"], "1 Cup(227g)")

    def test_missing_serving_weight_preserves_per_serving_but_does_not_scale(self):
        parsed = parse_food_label(
            "4 servings per container\nServing size 1 cup\n"
            "Amount per serving\nCalories 280\nTotal Fat 10 g"
        )
        result = normalize_nutrition(parsed)

        self.assertEqual(result["per_serving"]["total_fat"], 10.0)
        self.assertEqual(result["per_100g"], {})
        self.assertEqual(result["whole_package"]["total_fat"], 40.0)
        self.assertTrue(any("weight is missing or invalid" in warning for warning in result["warnings"]))

    def test_missing_servings_count_does_not_calculate_whole_package(self):
        parsed = parse_food_label(
            "Serving size 30 g\nAmount per serving\nCalories 100\nTotal Fat 3 g"
        )
        result = normalize_nutrition(parsed)

        self.assertEqual(result["per_100g"]["total_fat"], 10.0)
        self.assertEqual(result["per_serving"]["total_fat"], 3.0)
        self.assertEqual(result["whole_package"], {})
        self.assertTrue(any("servings per container" in warning for warning in result["warnings"]))

    def test_invalid_serving_weight_does_not_calculate_per_100g(self):
        parsed = parse_food_label(
            "4 servings per container\nServing size 0 g\n"
            "Amount per serving\nCalories 100\nTotal Fat 3 g"
        )
        result = normalize_nutrition(parsed)

        self.assertEqual(result["per_serving"]["total_fat"], 3.0)
        self.assertEqual(result["per_100g"], {})
        self.assertEqual(result["whole_package"]["total_fat"], 12.0)

    def test_reviewed_rows_are_excluded_without_losing_real_zero(self):
        parsed = parse_food_label(
            "2 servings per container\nServing size 100 g\nAmount per serving\n"
            "Calories 439 per serving\nTotal fat 14.87 g\nTrans fat 0 g\n"
            "Monounsaturated fat 4.89 g\n"
            "Protein 0.00 mcg\nIron 619.51 mg\n20.71 g"
        )
        result = normalize_nutrition(parsed)
        self.assertEqual(result["per_serving"]["trans_fat"], 0.0)
        self.assertEqual(result["per_serving"]["monounsaturated_fat"], 4.89)
        self.assertEqual(result["per_100g"]["total_fat"], 14.87)
        self.assertEqual(result["whole_package"]["energy_kcal"], 878.0)
        self.assertNotIn("protein", result["per_serving"])
        self.assertNotIn("iron", result["per_serving"])
        self.assertTrue(result["nutrition_review"])
        self.assertTrue(any("excluded from normalization" in warning for warning in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
