import sys
sys.path.insert(0, r'D:\Projects\NutriTrust\backend')

from nutrition_parser import parse_food_label, _extract_additives

# Test the exact ingredients text from the failing test
ingredients_text = "Ingredients: oats, sugar, cocoa, raising agent (500)\nContains: milk\nMay contain traces of soy"

# Test parse_food_label with ingredients_only=True
parsed = parse_food_label(ingredients_text, ingredients_only=True)
print(f"ingredients: {parsed['ingredients']!r}")
print(f"additives_tags: {parsed['additives_tags']!r}")

# Test _extract_additives directly
result = _extract_additives(
    parsed['ingredients'] or ingredients_text,
    name_text=parsed['ingredients'],
    spaced_e=bool(parsed['ingredients']),
)
print(f"_extract_additives result: {result!r}")

# Also test with just the raw text
result2 = _extract_additives(
    ingredients_text,
    name_text=None,
    spaced_e=False,
)
print(f"_extract_additives (raw) result: {result2!r}")

# Check what 3-4 digit numbers are in the text
import re
all_nums = re.findall(r"\b(\d{3,4})\b", ingredients_text)
print(f"All 3-4 digit numbers in text: {all_nums}")

# Check the readable text from parse_food_label
print(f"readable_text would be the full text")