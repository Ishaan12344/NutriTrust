import re

text1 = "INGREDIENTS: Wheat flour, raising agents (503(ii), 500(ii)), emulsifier (322 (soy lecithin)), sodium benzoate, antioxidant (319)"

# The current pattern from nutrition_parser.py
pattern3 = r"[\(\[\,]\s*(\d{3,4})\s*(?:\([a-z0-9]+\))?\s*[\)\]\,]"

# Let's see all possible matches with finditer
print("=== Current pattern 3 matches ===")
for m in re.finditer(pattern3, text1):
    print(f"  Full: '{m.group()}' -> number: '{m.group(1)}' at pos {m.start()}-{m.end()}")

# Now try a more permissive pattern
pattern3b = r"[\(\[\,]\s*(\d{3,4})\s*\(?[a-z0-9]*\)?\s*[\)\]\,]"
print("\n=== Modified pattern 3b matches ===")
for m in re.finditer(pattern3b, text1):
    print(f"  Full: '{m.group()}' -> number: '{m.group(1)}' at pos {m.start()}-{m.end()}")

# Try to find (500(ii)) specifically
print("\n--- Looking for 500 specifically ---")
for find in re.finditer(r"\((\d{3,4})ii\)", text1):
    print(f"  Found: '{find.group()}' -> number: '{find.group(1)}'")

# And (500(ii), with comma
print("\n--- Looking for 500(ii), format ---")
for m in re.finditer(r"\((\d{3,4})(?:\(ii\))?,\s*", text1):
    print(f"  Found: '{m.group(0)}' -> number: '{m.group(1)}'")

# And all parenthesized 3-4 digit numbers with optional (ii)
print("\n--- All parenthesized 3-4 digit numbers with (ii) ---")
for m in re.finditer(r"\((\d{3,4})(?:\(ii\))?\)", text1):
    print(f"  Found: '{m.group(0)}' -> number: '{m.group(1)}'")

# What about matching INS codes like INS 211, 319, 322, 500, 503?
print("\n--- Looking for INS codes ---")
# Pattern: INS 211, INS 319, etc.
for m in re.finditer(r"\bins (\d{3,4})\b", text1, re.IGNORECASE):
    print(f"  Found INS: '{m.group()}' -> number: '{m.group(1)}'")

# What about just "ins" as a word followed by digits
print("\n--- 'ins' followed by digits ---")
for m in re.finditer(r"\bins\d{3,4}\b", text1, re.IGNORECASE):
    print(f"  Found: '{m.group()}'")

# Check if "sodium benzoate" contains any known additive name patterns
print("\n--- Checking for additive name patterns ---")
additive_keywords = ["sodium benzoate", "antioxidant", "emulsifier", "raising agent", "lecithin"]
for kw in additive_keywords:
    if kw in text1:
        print(f"  Found: '{kw}'")