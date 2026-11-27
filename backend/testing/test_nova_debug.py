import sys
sys.path.insert(0, r'D:\Projects\NutriTrust\backend')

from nova_engine import classify_nova

# Test ingredients from the failing test
ingredients_text = "Wheat flour, sugar, edible vegetable oil, raising agents (503(ii), 500(ii)), sodium benzoate, antioxidant (319)\nContains: wheat"

result = classify_nova({"ingredients_text": ingredients_text})
print(f"NOVA result: {result}")

# Also test with just the simple ingredient text
ingredients_text2 = "oats, sugar, cocoa, raising agent (500)"
result2 = classify_nova({"ingredients_text": ingredients_text2})
print(f"NOVA result 2: {result2}")