import re

text1 = "INGREDIENTS: Wheat flour, raising agents (503(ii), 500(ii)), emulsifier (322 (soy lecithin)), sodium benzoate, antioxidant (319)"

# Current pattern 3
pattern3_old = r"[\(\[\,&]\s*(\d{3,4})\s*(?:\([a-z0-9]+\))?\s*[\)\]\,&]"
print("=== Old pattern 3 ===")
for m in re.finditer(pattern3_old, text1):
    print(f"  Full: '{m.group()}' -> number: '{m.group(1)}'")

# New pattern: just find (NNN) or [NNN] where NNN is 3-4 digits
pattern3_new1 = r"[\(\[]\s*(\d{3,4})"
print("\n=== New pattern 3a: [(\[\s*(\d{3,4}) ===")
for m in re.finditer(pattern3_new1, text1):
    print(f"  Full: '{m.group()}' -> number: '{m.group(1)}'")

# Pattern: find (NNN) anywhere in text
pattern3_new2 = r"\((\d{3,4})"
print("\n=== New pattern 3b: \((\d{3,4}) ===")
for m in re.finditer(pattern3_new2, text1):
    print(f"  Full: '{m.group(0)}' -> number: '{m.group(1)}'")

# Pattern: find all 3-4 digit numbers in parentheses or brackets
pattern3_new3 = r"(?:\(|\[)(\d{3,4})(?:\)|\])"
print("\n=== New pattern 3c: (?:\(|\[)(\d{3,4})(?:\)|\]) ===")
for m in re.finditer(pattern3_new3, text1):
    print(f"  Full: '{m.group(0)}' -> number: '{m.group(1)}'")

# Pattern: match (503(ii)) or (500(ii)) or (319)
pattern3_new4 = r"\((\d{3,4})(?:\(ii\))?\)"
print("\n=== New pattern 3d: \((\d{3,4})(?:\(ii\))?\) ===")
for m in re.finditer(pattern3_new4, text1):
    print(f"  Full: '{m.group(0)}' -> number: '{m.group(1)}'")

# Pattern: match (503(ii), or (500(ii)), or (319)
pattern3_new5 = r"\((\d{3,4})(?:\(ii\))?,\s*"
print("\n=== New pattern 3e: \((\d{3,4})(?:\(ii\))?,\s* ===")
for m in re.finditer(pattern3_new5, text1):
    print(f"  Full: '{m.group(0)}' -> number: '{m.group(1)}'")

# What about just finding all digit sequences that could be additives?
# Any 3-4 digit number that's not part of a year or other non-additive context
print("\n--- All 3-4 digit numbers in the text ---")
for m in re.finditer(r"\b(\d{3,4})\b", text1):
    print(f"  Number: '{m.group(1)}' at pos {m.start()}-{m.end()}")

# Filter to additive range (100-1599)
print("\n--- 3-4 digit numbers in additive range (100-1599) ---")
for m in re.finditer(r"\b(\d{3,4})\b", text1):
    val = int(m.group(1))
    if 100 <= val <= 1599:
        print(f"  Number: '{m.group(1)}' (in range) at pos {m.start()}-{m.end()}")