import re

text = "INGREDIENTS: Wheat flour, raising agents (503(ii), 500(ii)), emulsifier (322 (soy lecithin)), sodium benzoate, antioxidant (319)"

additives = set()

# Step 1: E-numbers
e_pattern = r"\b[eE][\s\-]?(\d{3,4}[a-z]?)\b"
for num in re.findall(e_pattern, text):
    additives.add(f"E{num.upper()}")
print(f"After step 1 (E-numbers): {additives}")

# Step 2: INS numbers
for num, _ in re.findall(
    r"\bins[\s\-]?(\d{3,4})\s*\(?([a-z0-9]*)\)?", text, re.IGNORECASE
):
    additives.add(f"E{num.upper()}")
print(f"After step 2 (INS): {additives}")

# Step 3: Bracketed numbers
for num in re.findall(
    r"[\(\[\,&]\s*(\d{3,4})\s*(?:\([a-z0-9]+\))?\s*[\)\]\,&]", text, re.IGNORECASE
):
    if 100 <= int(num) <= 1599:
        additives.add(f"E{num}")
print(f"After step 3 (bracketed): {additives}")

# Step 4: Keyword numbers
for num in re.findall(
    r"(?:raising agent|dough conditioner|emulsifier|preservative|stabiliser|"
    r"stabilizer|colour|color|acidity regulator)s?\s*\[?\(?\s*(\d{3,4})",
    text, re.IGNORECASE,
):
    if 100 <= int(num) <= 1599:
        additives.add(f"E{num}")
print(f"After step 4 (keyword): {additives}")

# Step 5: Fallback - all 3-4 digit numbers in range
for m in re.finditer(r"\b(\d{3,4})\b", text):
    try:
        val = int(m.group(1))
        if 100 <= val <= 1599:
            code = f"E{val}"
            if code not in additives:
                additives.add(code)
    except ValueError:
        continue
print(f"After step 5 (fallback): {additives}")

# Step 6: Reverse name mapping
lowered = "sodium benzoate antioxidant raising agents emulsifier wheat flour".casefold()
name_to_code_map = {
    "sodium benzoate": "E211",
    "benzoic acid": "E211",
}
for name, code in name_to_code_map.items():
    if name.casefold() in lowered:
        additives.add(code)
print(f"After step 6 (name mapping): {additives}")

# What does each pattern individually find?
print("\n--- Pattern details ---")

# Pattern 3 details
matches3 = re.findall(
    r"[\(\[\,&]\s*(\d{3,4})\s*(?:\([a-z0-9]+\))?\s*[\)\]\,&]", text, re.IGNORECASE
)
print(f"Pattern 3 matches (findall): {matches3}")

# Keyword pattern details
matches4 = re.findall(
    r"(?:raising agent|dough conditioner|emulsifier|preservative|stabiliser|"
    r"stabilizer|colour|color|acidity regulator)s?\s*\[?\(?\s*(\d{3,4})",
    text, re.IGNORECASE,
)
print(f"Pattern 4 matches (findall): {matches4}")

# All 3-4 digit numbers
all_nums = re.findall(r"\b(\d{3,4})\b", text)
print(f"All 3-4 digit numbers: {all_nums}")