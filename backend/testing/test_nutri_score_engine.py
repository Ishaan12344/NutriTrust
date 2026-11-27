import unittest

from nutri_score_engine import ALGORITHM_VERSION, calculate_nutri_score


class NutriScoreEngineTests(unittest.TestCase):
    def test_official_worked_example_solid_food(self):
        result = calculate_nutri_score({
            "name": "Wholegrain bread-like product",
            "energy_kj": 900,
            "sugars": 3,
            "saturated_fat": 0.5,
            "salt": 0.3,
            "fibre": 6,
            "protein": 10,
            "fruit_vegetable_percent": 0,
        })
        self.assertEqual(result["algorithm_version"], ALGORITHM_VERSION)
        self.assertEqual(result["points"]["negative_total"], 3)
        self.assertEqual(result["points"]["positive_total"], 7)
        self.assertEqual(result["score"], -4)
        self.assertEqual(result["grade"], "A")
        self.assertEqual(result["status"], "calculated")
        self.assertIn("protein", result["points"]["positive"])

    def test_official_worked_example_beverage_is_not_grade_a(self):
        result = calculate_nutri_score({
            "category": "Milk and dairy beverages",
            "energy_kj": 145,
            "sugars": 5,
            "saturated_fat": 0.1,
            "salt": 0.1,
            "protein": 3.5,
            "fibre": 0,
            "fruit_vegetable_percent": 0,
        })
        self.assertEqual(result["category_key"], "beverage")
        self.assertEqual(result["points"]["negative_total"], 5)
        self.assertEqual(result["points"]["positive_total"], 7)
        self.assertEqual(result["score"], -2)
        self.assertEqual(result["grade"], "B")

    def test_water_uses_grade_a_rule_without_nutrition(self):
        result = calculate_nutri_score({"category": "Mineral waters"})
        self.assertEqual(result["status"], "calculated_water_rule")
        self.assertEqual(result["grade"], "A")

    def test_threshold_boundaries_and_fvl_point_jump(self):
        at_boundary = calculate_nutri_score({
            "energy_kj": 335, "sugars": 3.4, "saturated_fat": 1, "salt": 0.2,
        })
        self.assertEqual(at_boundary["points"]["negative_total"], 0)
        self.assertEqual(at_boundary["grade"], "A")

        over_boundary = calculate_nutri_score({
            "energy_kj": 335.1, "sugars": 3.5, "saturated_fat": 1.1, "salt": 0.21,
        })
        self.assertEqual(over_boundary["points"]["negative_total"], 4)

        fvl = calculate_nutri_score({
            "energy_kj": 500, "sugars": 0, "saturated_fat": 0, "salt": 0,
            "fruit_vegetable_percent": 81,
        })
        self.assertEqual(fvl["points"]["positive"]["fruit_vegetable_percent"]["points"], 5)
        self.assertEqual(fvl["score"], -4)

    def test_missing_mandatory_input_prevents_grade(self):
        result = calculate_nutri_score({
            "energy_kcal": 250, "sugars": 5, "saturated_fat": 2,
        })
        self.assertEqual(result["status"], "incomplete_data")
        self.assertIn("salt", result["missing_inputs"])
        self.assertIsNone(result["score"])
        self.assertIsNone(result["grade"])

    def test_invalid_values_are_rejected_not_silently_zeroed(self):
        result = calculate_nutri_score({
            "energy_kj": 500, "sugars": -3, "saturated_fat": 2, "salt": 0.5,
        })
        self.assertIn("sugars", result["missing_inputs"])
        self.assertTrue(any("Negative value" in warning for warning in result["warnings"]))

    def test_fats_category_exception_excludes_protein_at_high_negative_points(self):
        result = calculate_nutri_score({
            "name": "Vegetable oil",
            "energy_kcal": 884,
            "sugars": 0,
            "saturated_fat": 20,
            "total_fat": 100,
            "salt": 0,
            "fibre": 8,
            "protein": 20,
        })
        self.assertEqual(result["category_key"], "fats_oils_nuts_seeds")
        self.assertFalse(result["points"]["protein_points_used"])
        self.assertEqual(result["points"]["negative_total"], 8)
        self.assertEqual(result["score"], 3)
        self.assertEqual(result["grade"], "C")

    def test_red_meat_protein_points_are_capped(self):
        result = calculate_nutri_score({
            "name": "Beef steak",
            "energy_kj": 1000,
            "sugars": 0,
            "saturated_fat": 5,
            "salt": 0.5,
            "protein": 20,
        })
        self.assertEqual(result["category_key"], "red_meat")
        self.assertEqual(result["points"]["positive"]["protein"]["points"], 2)
        self.assertEqual(result["score"], 6)
        self.assertTrue(any("Red meat protein" in item for item in result["exceptions"]))


if __name__ == "__main__":
    unittest.main()
