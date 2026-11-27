import unittest
from food_data_merger import merge_product_data


class MergeTests(unittest.TestCase):
    def test_ocr_ingredients_win_and_off_fills_product_fields(self):
        merged = merge_product_data(
            {
                "ingredients": "oats, sugar",
                "ingredient_items": ["oats", "sugar"],
                "allergen_analysis": {
                    "declared": ["milk"],
                    "may_contain": [],
                    "ingredient_terms_detected": [],
                    "declaration_text": "Contains milk",
                    "precautionary_text": None,
                    "status": "declared_on_label",
                    "review_required": False,
                },
                "warnings": [],
            },
            {"per_100g": {"sugar": 12.0}, "per_serving": {"sugar": 6.0}},
            {
                "found": True,
                "barcode": "1234567890123",
                "product_name": "Example",
                "brands": "Brand",
                "ingredients_text": "old ingredients",
                "allergens_tags": ["en:milk"],
                "traces_tags": [],
                "nutrition_per_100g": {"sugar": {"value": 10, "unit": "g"}},
                "nutrition_basis": "per_100g",
                "available_fields": ["product_name"],
            },
        )
        self.assertEqual(merged["ingredients"]["text"], "oats, sugar")
        self.assertEqual(merged["product"]["name"], "Example")
        self.assertEqual(merged["nutrition"]["per_100g"]["sugar"]["value"], 12.0)
        self.assertEqual(
            merged["nutrition"]["per_100g"]["sugar"]["source"], "ocr_label"
        )
        self.assertEqual(len(merged["nutrition"]["conflicts"]), 1)
        self.assertEqual(merged["allergens"]["traces_tags"], [])

    def test_off_fills_missing_nutrition(self):
        merged = merge_product_data(
            {"warnings": [], "allergen_analysis": {"review_required": True}},
            {"per_100g": {}, "per_serving": {}},
            {
                "found": True,
                "nutrition_per_100g": {"protein": {"value": 7, "unit": "g"}},
                "nutrition_basis": "per_100g",
                "available_fields": [],
            },
        )
        self.assertEqual(
            merged["nutrition"]["per_100g"]["protein"]["source"], "open_food_facts"
        )

    def test_no_off_data_is_supported(self):
        merged = merge_product_data(
            {"warnings": [], "allergen_analysis": {"review_required": True}}, {}, None
        )
        self.assertFalse(merged["open_food_facts"]["found"])
        self.assertFalse(
            any("Open Food Facts data was not available" in warning for warning in merged["warnings"])
        )


if __name__ == "__main__":
    unittest.main()
