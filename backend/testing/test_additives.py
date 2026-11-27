import re

def _extract_additives(text):
    additives = set()
    combined = text
    
    # 1. Standard E-numbers
    e_matches = re.findall(r"\b[eE][\s\-]?(\d{3,4}[a-z]?)\b", combined)
    for num in e_matches:
        additives.add(f"E{num.upper()}")
    
    # 2. Standard INS numbers
    ins_matches = re.findall(r"\bins[\s\-]?(\d{3,4})\s*\(?([a-z0-9]*)\)?", combined, re.IGNORECASE)
    for num, sub in ins_matches:
        additives.add(f"E{num.upper()}")
    
    # 3. Bracketed / Parenthesized additive numbers
    bracketed_matches = re.findall(r"[\(\[\,]\s*(\d{3,4})\s*(?:\([a-z0-9]+\))?\s*[\)\]\,]", combined)
    for num in bracketed_matches:
        if 100 <= int(num) <= 1599:
            additives.add(f"E{num}")
    
    # 4. Keyword search
    keyword_numbers = re.findall(r"(?:raising agent|dough conditioner|emulsifier|preservative|stabiliser|colour|color|acidity regulator)s?\s*\[?\(?\s*(\d{3,4})", combined, re.IGNORECASE)
    for num in keyword_numbers:
        if 100 <= int(num) <= 1599:
            additives.add(f"E{num}")
    
    return sorted(list(additives))

# Test 1: from test_nutrition_parser.py
text1 = "INGREDIENTS: Wheat flour, raising agents (503(ii), 500(ii)), emulsifier (322 (soy lecithin)), sodium benzoate, antioxidant (319)"
result1 = _extract_additives(text1)
print(f"Test 1 result: {result1}")
print(f"Test 1 expected: ['E211', 'E319', 'E322', 'E500', 'E503']")
print(f"Test 1 match: {result1 == ['E211', 'E319', 'E322', 'E500', 'E503']}")

# Test 2: from test_main_pipeline.py  
text2 = "INGREDIENTS: Wheat flour, sugar, edible vegetable oil, raising agents (503(ii), 500(ii)), sodium benzoate, antioxidant (319)\nContains: wheat"
result2 = _extract_additives(text2)
print(f"\nTest 2 result: {result2}")
print(f"Test 2 expected: ['E211', 'E319', 'E500', 'E503']")
print(f"Test 2 match: {result2 == ['E211', 'E319', 'E500', 'E503']}")

# Debug: show what each pattern finds
print("\n--- Debug ---")
combined = text1

# Pattern 1
e_matches = re.findall(r"\b[eE][\s\-]?(\d{3,4}[a-z]?)\b", combined)
print(f"Pattern 1 (E-numbers): {e_matches}")

# Pattern 2
ins_matches = re.findall(r"\bins[\s\-]?(\d{3,4})\s*\(?([a-z0-9]*)\)?", combined, re.IGNORECASE)
print(f"Pattern 2 (INS numbers): {ins_matches}")

# Pattern 3
bracketed_matches = re.findall(r"[\(\[\,]\s*(\d{3,4})\s*(?:\([a-z0-9]+\))?\s*[\)\]\,]", combined)
print(f"Pattern 3 (bracketed): {bracketed_matches}")

# Pattern 4
keyword_numbers = re.findall(r"(?:raising agent|dough conditioner|emulsifier|preservative|stabiliser|colour|color|acidity regulator)s?\s*\[?\(?\s*(\d{3,4})", combined, re.IGNORECASE)
print(f"Pattern 4 (keyword): {keyword_numbers}")