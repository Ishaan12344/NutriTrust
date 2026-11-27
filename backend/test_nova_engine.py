import unittest

from nova_engine import classify_nova


class NovaEngineTests(unittest.TestCase):
    def test_minimally_processed_food(self):
        result = classify_nova({"ingredients_text": "Fresh apples"})
        self.assertEqual(result["group"], 1)
        self.assertEqual(result["status"], "classified")
        self.assertIn("no added culinary substances", " ".join(result["reasons"]))

    def test_processed_culinary_ingredient(self):
        result = classify_nova({"ingredients_text": "Olive oil"})
        self.assertEqual(result["group"], 2)
        self.assertEqual(result["group_name"], "Processed culinary ingredients")

    def test_processed_food(self):
        result = classify_nova({"ingredients_text": "Flour, water, salt, yeast"})
        self.assertEqual(result["group"], 3)
        self.assertEqual(result["status"], "classified")

    def test_cosmetic_marker_makes_ultra_processed(self):
        result = classify_nova({
            "ingredients_text": "Flour, water, salt, yeast, emulsifier, natural colour",
        })
        self.assertEqual(result["group"], 4)
        self.assertEqual(result["evidence_strength"], "direct_marker")
        self.assertTrue(any("emulsifier" in reason for reason in result["reasons"]))

    def test_ambiguous_processing_aid_is_not_automatic_group_four(self):
        result = classify_nova({
            "ingredients_text": "Oats, sugar, cocoa, raising agent (500)",
        })
        self.assertIsNone(result["group"])
        self.assertEqual(result["status"], "uncertain")
        self.assertIn("raising agent", result["uncertainty"])

    def test_missing_ingredient_list_is_undetermined(self):
        result = classify_nova({"ingredients_text": None})
        self.assertIsNone(result["group"])
        self.assertEqual(result["status"], "undetermined")
        self.assertIn("ingredient list", result["missing_information"])

    def test_external_group_is_reported_when_rules_are_inconclusive(self):
        result = classify_nova({"ingredients_text": "Unknown compound blend", "nova_group": 4, "nova_source": "open_food_facts"})
        self.assertEqual(result["group"], 4)
        self.assertEqual(result["status"], "external_source")
        self.assertEqual(result["external_classification"]["source"], "open_food_facts")

    def test_no_numeric_confidence_is_returned(self):
        result = classify_nova({"ingredients_text": "Flour, water, salt, yeast, colour"})
        self.assertNotIn("confidence", result)
        self.assertNotIn("confidence_score", result)


if __name__ == "__main__":
    unittest.main()
