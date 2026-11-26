import sys
sys.path.insert(0, r'D:\Projects\NutriTrust\backend')

from nutrition_parser import _extract_additives

# Test 1: Ingredients text from the dual image test
ingredients_text = "Ingredients: oats, sugar, cocoa, raising agent (500)\nContains: milk\nMay contain traces of soy"
result1 = _extract_additives(ingredients_text or ingredients_text, name_text=ingredients_text, spaced_e=True)
print(f"Test 1 (ingredients only): {result1}")

# Test 2: Nutrition label text  
nutrition_text = "Product Name: Sample Bar\nIngredients: oats, sugar, cocoa\nContains: milk\nNutrition information per 100 g\nTotal Fat | 5 g\nProtein | 4 g"
result2 = _extract_additives(nutrition_text or nutrition_text, name_text=nutrition_text, spaced_e=False)
print(f"Test 2 (nutrition label): {result2}")

# Test 3: Just the number 100
result3 = _extract_additives("100 g", name_text="100 g", spaced_e=False)
print(f"Test 3 (just 100 g): {result3}")

# Test 4: 100 with other text
result4 = _extract_additives("per 100 g", name_text="per 100 g", spaced_e=False)
print(f"Test 4 (per 100 g): {result4}")

# Test 5: The actual call from parse_food_label
from nutrition_parser import parse_food_label
parsed = parse_food_label(ingredients_text, ingredients_only=True)
print(f"\nparse_food_label ingredients: {parsed['ingredients']!r}")
print(f"parse_food_label additives: {parsed['additives_tags']!r}")