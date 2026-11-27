import unittest
from nutrition_parser import parse_food_label


class NutritionParserTests(unittest.TestCase):
    def test_plain_text_ingredients_and_allergens(self):
        result = parse_food_label(
            "Ingredients: Wheat flour, sugar, cocoa powder, milk solids\n"
            "Contains: Wheat, Milk\n"
            "May contain traces of soy and peanuts.\n"
            "Nutrition Facts\nServing size 30 g\nCalories 150\nTotal Fat 5 g"
        )
        self.assertEqual(result["ingredients"], "Wheat flour, sugar, cocoa powder, milk solids")
        self.assertEqual(result["allergen_analysis"]["declared"], ["milk", "wheat"])
        self.assertEqual(result["allergen_analysis"]["may_contain"], ["soy", "peanut"])
        self.assertEqual(result["nutrition"]["total_fat"], {"value": 5.0, "unit": "g"})

    def test_explicit_product_identity_is_extracted(self):
        result = parse_food_label("Product Name: Oat Bar\nBrand: Grain Co")
        self.assertEqual(result["product_name"], "Oat Bar")
        self.assertEqual(result["brand"], "Grain Co")

    def test_markdown_heading_and_parenthetical_ingredients(self):
        result = parse_food_label(
            "# Ingredients\nWheat flour, sugar, cocoa powder (cocoa mass, cocoa butter), milk solids\n\n"
            "**Allergen information:** Contains wheat and milk.\nMay contain traces of soy.\n\n"
            "Nutrition Facts\nServing size: 1 bar (40 g)\nCalories 200\nTotal Fat 8 g"
        )
        self.assertIn("cocoa powder (cocoa mass, cocoa butter)", result["ingredient_items"])
        self.assertEqual(result["allergen_analysis"]["declared"], ["milk", "wheat"])
        self.assertEqual(result["allergen_analysis"]["may_contain"], ["soy"])

    def test_html_table(self):
        result = parse_food_label(
            "<html><body><p>INGREDIENTS: Rice, salt, spices.</p>"
            "<p>Allergens: None declared</p><table><tr><td>Total Fat</td><td>3 g</td><td>4%</td></tr></table></body></html>"
        )
        self.assertEqual(result["ingredients"], "Rice, salt, spices.")
        self.assertEqual(result["nutrition"]["total_fat"], {"value": 3.0, "unit": "g"})
        self.assertTrue(result["allergen_analysis"]["review_required"])

    def test_concatenated_serving_headings_and_cup_weight(self):
        result = parse_food_label(
            "4 servings per containerServing size 1 Cup(227g)\n"
            "Amount per serving\nCalories 280"
        )
        self.assertEqual(result["servings_per_container"], 4)
        self.assertEqual(result["serving_size"], {"text": "1 Cup(227g)", "weight_g": 227.0})
        self.assertEqual(result["calories_per_serving_kcal"], 280.0)

    def test_serving_size_supported_formats(self):
        cases = [
            ("Serving size 30 g", "30 g", 30.0),
            ("Serving size 2 pieces (45 g)", "2 pieces (45 g)", 45.0),
        ]
        for text, expected_text, expected_weight in cases:
            with self.subTest(text=text):
                parsed = parse_food_label(text)
                self.assertEqual(parsed["serving_size"]["text"], expected_text)
                self.assertEqual(parsed["serving_size"]["weight_g"], expected_weight)

    def test_count_or_volume_without_explicit_weight_is_preserved_without_guess(self):
        parsed = parse_food_label("Serving size 1 cup")
        self.assertEqual(parsed["serving_size"], {"text": "1 cup", "weight_g": None})
        self.assertTrue(any("explicit weight" in warning for warning in parsed["warnings"]))

    def test_zero_and_negative_serving_sizes_are_invalid(self):
        for text in ("Serving size 0 g", "Serving size -30 g"):
            with self.subTest(text=text):
                parsed = parse_food_label(text)
                self.assertIsNone(parsed["serving_size"]["weight_g"])

    def test_nonpositive_servings_per_container_are_rejected(self):
        for count in ("0", "-2"):
            with self.subTest(count=count):
                parsed = parse_food_label(f"{count} servings per container")
                self.assertIsNone(parsed["servings_per_container"])
                self.assertTrue(any("positive whole number" in warning for warning in parsed["warnings"]))

    def test_empty_ocr_is_not_success(self):
        result = parse_food_label("  ")
        self.assertEqual(result["extraction"]["status"], "failed")
        self.assertTrue(result["extraction"]["needs_review"])
        self.assertIsNone(result["ingredients"])

    def test_jamun_mix_label_rows_keep_valid_amounts_and_review_suspicious_rows(self):
        parsed = parse_food_label(
            "2 servings per container\nServing size 3.5 oz (100 g), around 20 pieces\n"
            "Amount per serving\nCalories 439 per serving\n"
            "Total fat | 14.87 g | 22%\nSaturated fat | 8.29 g\n"
            "Monounsaturated fat | 4.89 g\nPolyunsaturated fat | 1.66 g\n"
            "Trans fat | 0 g\nCholesterol | 0 mg\nSodium | 419.96 mg\n"
            "Total carbohydrate | 55.75 g\nDietary fiber | 1.78 g\n"
            "Total sugars | 19.79 g\nAdded sugars | 0 g\n"
            "20.71 g\nProtein | 0.00 mcg\nVitamin D | 724.16 mg\n"
            "Calcium | 0.67 mg\nIron | 619.51 mg"
        )
        self.assertEqual(parsed["servings_per_container"], 2)
        self.assertEqual(parsed["serving_size"]["weight_g"], 100.0)
        self.assertEqual(parsed["calories_per_serving_kcal"], 439.0)
        self.assertEqual(parsed["nutrition"]["total_fat"]["value"], 14.87)
        self.assertEqual(parsed["nutrition"]["monounsaturated_fat"]["value"], 4.89)
        self.assertEqual(parsed["nutrition"]["polyunsaturated_fat"]["value"], 1.66)
        self.assertEqual(parsed["daily_values_percent"]["total_fat"], 22.0)
        self.assertEqual(parsed["nutrition"]["trans_fat"]["value"], 0.0)
        self.assertEqual(parsed["nutrition"]["added_sugars"]["value"], 0.0)
        self.assertNotIn("protein", parsed["nutrition"])
        states = {item.get("nutrient"): item["status"] for item in parsed["nutrition_review"]}
        self.assertEqual(states["protein"], "invalid")
        self.assertEqual(states["iron"], "suspicious")
        self.assertIn("unresolved", [item["status"] for item in parsed["nutrition_review"]])
        self.assertIn("unresolved", [item["status"] for item in parsed["nutrition_review"] if "Vitamin D" in item["row"]])

    def test_energy_format_and_html_column_association(self):
        # kJ + kcal lines must not read the kJ number as kcal; kJ-only converts.
        kj_and_kcal = parse_food_label("Energy 1460 kJ / 350 kcal\nProtein 4 g")
        self.assertEqual(kj_and_kcal["calories_per_serving_kcal"], 350.0)
        kj_only = parse_food_label("Energy 1460 kJ\nProtein 4 g")
        self.assertAlmostEqual(kj_only["calories_per_serving_kcal"], round(1460 / 4.184, 2))
        energy = parse_food_label("Energy 439 kcal\nTotal fat 14.87 g\nProtein 4 g")
        self.assertEqual(energy["calories_per_serving_kcal"], 439.0)
        table = parse_food_label(
            "<table><tr><td>Sodium</td><td>419.96 mg</td><td>18%</td></tr>"
            "<tr><td>Dietary fiber</td><td>1.78 g</td><td>6%</td></tr></table>"
        )
        self.assertEqual(table["nutrition"]["sodium"], {"value": 419.96, "unit": "mg"})
        self.assertEqual(table["daily_values_percent"]["sodium"], 18.0)
        self.assertEqual(table["nutrition"]["dietary_fiber"], {"value": 1.78, "unit": "g"})
        bare = parse_food_label("Carbohydrate | 45 g\nProtein | 10 g")
        self.assertEqual(bare["nutrition"]["total_carbohydrate"], {"value": 45.0, "unit": "g"})

    def test_per_serving_and_per_100g_columns_prefer_per_100g_when_present(self):
        table = parse_food_label(
            "<table>"
            "<tr><th>Nutrient</th><th>Per serving (30 g)</th><th>Per 100 g</th></tr>"
            "<tr><td>Energy</td><td>110 kcal</td><td>350 kcal</td></tr>"
            "<tr><td>Protein</td><td>3 g</td><td>10 g</td></tr>"
            "<tr><td>Carbohydrate</td><td>14 g</td><td>45 g</td></tr>"
            "<tr><td>Total fat</td><td>2 g</td><td>6 g</td></tr>"
            "</table>"
        )
        self.assertEqual(table["reference_basis"]["detected"], "per_100g")
        self.assertEqual(table["calories_per_serving_kcal"], 350.0)
        self.assertEqual(table["nutrition"]["protein"], {"value": 10.0, "unit": "g"})
        self.assertEqual(table["nutrition"]["total_carbohydrate"], {"value": 45.0, "unit": "g"})
        self.assertEqual(table["nutrition"]["total_fat"], {"value": 6.0, "unit": "g"})


    def test_additives_and_salt_are_recognized(self):
        parsed = parse_food_label(
            "Ingredients: Wheat flour, salt, raising agent [503(ii)], "
            "preservative (223), INS 621\n"
            "Nutrition Facts\nSalt 1 g"
        )
        self.assertEqual(parsed["additives_tags"], ["E223", "E503", "E621"])
        self.assertEqual(parsed["nutrition"]["sodium"], {"value": 400.0, "unit": "mg"})

    def test_ingredients_only_falls_back_to_full_text(self):
        text = "Wheat flour, sugar, cocoa powder, milk solids"
        self.assertIsNone(parse_food_label(text)["ingredients"])
        parsed = parse_food_label(text, ingredients_only=True)
        self.assertEqual(parsed["ingredients"], text)

    def test_additives_in_comma_lists_brackets_and_names(self):
        parsed = parse_food_label(
            "INGREDIENTS: Wheat flour, raising agents (503(ii), 500(ii)), "
            "emulsifier (322 (soy lecithin)), sodium benzoate, antioxidant (319)",
            ingredients_only=True,
        )
        self.assertEqual(
            parsed["additives_tags"], ["E211", "E319", "E322", "E500", "E503"]
        )

    def test_full_text_fallback_does_not_read_vitamin_e_as_an_additive(self):
        parsed = parse_food_label("Nutrition Facts\nVitamin E 100 mcg")
        self.assertEqual(parsed["additives_tags"], [])

    def test_sarvam_markdown_pipe_table_and_split_sugar_line(self):
        ocr_text = (
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
        parsed = parse_food_label(ocr_text)
        self.assertEqual(parsed["reference_basis"]["detected"], "per_100g")
        self.assertEqual(parsed["calories_per_serving_kcal"], 480.0)
        self.assertEqual(parsed["nutrition"]["total_fat"], {"value": 20.0, "unit": "g"})
        self.assertEqual(parsed["nutrition"]["saturated_fat"], {"value": 10.0, "unit": "g"})
        self.assertEqual(parsed["nutrition"]["total_carbohydrate"], {"value": 65.0, "unit": "g"})
        self.assertEqual(parsed["nutrition"]["total_sugars"], {"value": 24.0, "unit": "g"})
        self.assertEqual(parsed["nutrition"]["protein"], {"value": 7.0, "unit": "g"})
        self.assertEqual(parsed["nutrition"]["sodium"], {"value": 300.0, "unit": "mg"})
        self.assertFalse(
            any(item.get("nutrient") == "total_sugars" for item in parsed["nutrition_review"])
        )


if __name__ == "__main__":
    unittest.main()
