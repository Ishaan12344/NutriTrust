import re

text1 = "INGREDIENTS: Wheat flour, raising agents (503(ii), 500(ii)), emulsifier (322 (soy lecithin)), sodium benzoate, antioxidant (319)"

# Pattern 3 detailed
pattern3 = r"[\(\[\,]\s*(\d{3,4})\s*(?:\([a-z0-9]+\))?\s*[\)\]\,]"
matches3 = [(m.start(), m.group()) for m in re.finditer(pattern3, text1)]
print(f"Pattern 3 matches: {matches3}")

# Try matching 500 specifically
for m in re.finditer(pattern3, text1):
    print(f"  Full match: '{m.group()}' at position {m.start()}-{m.end()}")
    print(f"  Captured number: '{m.group(1)}'")

# Also try with different patterns
print("\n--- Trying variations ---")

# Pattern that might match 500(ii))
pattern_a = r"[\(\[\,]\s*(\d{3,4})\)"
matches_a = re.findall(pattern_a, text1)
print(f"Pattern a (simple): {matches_a}")

# Pattern with (500 followed by anything)
pattern_b = r"\((\d{3,4})\)"
matches_b = re.findall(pattern_b, text1)
print(f"Pattern b: {matches_b}")

# Find all parenthesized numbers
pattern_c = r"\((\d{3,4}(?:\([a-z0-9]+\))?)\)"
matches_c = re.findall(pattern_c, text1)
print(f"Pattern c: {matches_c}")

# What about just finding all digit sequences in parentheses?
pattern_d = r"\(\d{3,4}\)"
matches_d = re.findall(pattern_d, text1)
print(f"Pattern d: {matches_d}")

# Check what's between parentheses
pattern_e = r"\(([^)]+)\)"
matches_e = re.findall(pattern_e, text1)
print(f"Pattern e (all paren contents): {matches_e}")

# Now try the actual _extract_additives function from nutrition_parser
def _extract_additives_v1(text):
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

result = _extract_additives_v1(text1)
print(f"\n_extract_additives result: {result}")
print(f"Expected: ['E211', 'E319', 'E322', 'E500', 'E503']")

# Now try the actual function from the module
from backend.nutrition_parser import _extract_additives as _extract_additives_real
result_real = _extract_additives_real(text1)
print(f"\nReal _extract_additives result: {result_real}")