import sys
sys.path.insert(0, r'D:\Projects\NutriTrust\backend')

from nutrition_parser import parse_food_label, _extract_additives

# Test with ingredients_only=True
parsed = parse_food_label(
    "INGREDIENTS: Wheat flour, raising agents (503(ii), 500(ii)), "
    "emulsifier (322 (soy lecithin)), sodium benzoate, antioxidant (319)",
    ingredients_only=True,
)

print(f"ingredients: {parsed['ingredients']}")
print(f"additives_tags: {parsed['additives_tags']}")
print(f"Expected: ['E211', 'E319', 'E322', 'E500', 'E503']")

# Also test _extract_additives directly with the same parameters
ingredients_text = parsed['ingredients']
result = _extract_additives(
    ingredients_text or "INGREDIENTS: Wheat flour, raising agents (503(ii), 500(ii)), emulsifier (322 (soy lecithin)), sodium benzoate, antioxidant (319)",
    name_text=ingredients_text,
    spaced_e=bool(ingredients_text),
)
print(f"\nDirect _extract_additives call: {result}")