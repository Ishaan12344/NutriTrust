import sys
sys.path.insert(0, r'D:\Projects\NutriTrust\backend')

from nutrition_parser import parse_food_label, _extract_section, _clean

# Test with ingredients_only=True
ocr_content = "INGREDIENTS: Wheat flour, raising agents (503(ii), 500(ii)), emulsifier (322 (soy lecithin)), sodium benzoate, antioxidant (319)"

# Step 1: _to_text_and_rows
from nutrition_parser import _to_text_and_rows
readable_text, rows = _to_text_and_rows(ocr_content)
print(f"readable_text: {readable_text!r}")
print(f"rows: {rows}")

# Step 2: _extract_section
heading_pattern = r"(?:ingredients?(?:\s+list)?|composition|contents?|noodles?|masala|tastemaker|seasoning|sauce|filling|crust)"
stop_pattern = r"\b(?:allergens?|contains|may\s+contain(?:\s+traces\s+of)?|nutrition(?:al)?\s+(?:information|facts|values?)|per\s+100\s*g|per\s+serving|storage|directions\s+for\s+use|manufactured\s+by|marketed\s+by|best\s+before|batch\s*(?:no|number)?|fssai|customer\s+care|net\s+quantity|serving\s+size|calories?|total\s+fat|saturated\s+fat|trans\s+fat|cholesterol|sodium|total\s+carbohydrate|total\s+carbs?|dietary\s+fiber|dietary\s+fibre|total\s+sugars?|added\s+sugars?|protein|calcium|iron|potassium)\b\s*:?"

ingredient_text = _extract_section(
    readable_text,
    heading_pattern,
    stop_pattern,
)
print(f"\ningredient_text from _extract_section: {ingredient_text!r}")

# Step 3: ingredients_only fallback
if ingredient_text is None and True:  # ingredients_only=True
    candidate = _clean(readable_text)
    print(f"candidate (full clean): {candidate!r}")
    if candidate and not re.search(
        r"\b(?:nutrition(?:al)?\s+(?:information|facts|values?)|per\s+100\s*g|calories?|"
        r"total\s+fat|saturated\s+fat|trans\s+fat|sodium|total\s+carbohydrate|protein)\b",
        candidate, 
    ):
        ingredient_text = candidate
        print(f"ingredient_text from fallback: {ingredient_text!r}")

# Step 4: Set result["ingredients"]
if ingredient_text:
    ingredient_text = re.sub(r"^\s*[-*•]\s*", "", ingredient_text)
    ingredient_text = _clean(ingredient_text)
    print(f"\nAfter clean: {ingredient_text!r}")
else:
    print("\ningredient_text is None/Falsy")