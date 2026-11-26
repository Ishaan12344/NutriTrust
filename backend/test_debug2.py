import re

def _clean(value: str) -> str:
    value = value.replace("\xa0", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\s*\n\s*", "\n", value)
    value = value.strip(" \t\r\n:;,")
    if value.startswith("-") and not re.match(r"-\s*\d", value):
        value = value.lstrip("-").lstrip()
    if value.endswith("-"):
        value = value.rstrip("-").rstrip()
    return value

def _extract_section(text: str, heading_pattern: str, stop_pattern="$") -> str | None:
    match = re.search(
        rf"(?is)(?:^|[\n|:]\s*)\s*(?:{heading_pattern})\s*:?\s*(.*?)(?={stop_pattern}|$)",
        text,
    )
    if not match:
        return None
    value = _clean(match.group(1))
    return value or None

heading_pattern = r"(?:ingredients?(?:\s+list)?|composition|contents?|noodles?|masala|tastemaker|seasoning|sauce|filling|crust)"
text = "INGREDIENTS: Wheat flour, raising agents (503(ii), 500(ii)), emulsifier (322 (soy lecithin)), sodium benzoate, antioxidant (319)"

match = re.search(
    rf"(?is)(?:^|[\n|:]\s*)\s*(?:{heading_pattern})\s*:?\s*(.*?)(?=$)",
    text,
)
if match:
    value = _clean(match.group(1))
    print(f"_extract_section result: '{value}'")
else:
    print("_extract_section: no match")

# Now test _extract_additives
from nutrition_parser import _extract_additives

ingredients_text = "Wheat flour, raising agents (503(ii), 500(ii)), emulsifier (322 (soy lecithin)), sodium benzoate, antioxidant (319)"
result = _extract_additives(
    ingredients_text or text,
    name_text=ingredients_text,
    spaced_e=bool(ingredients_text),
)
print(f"_extract_additives result: {result}")
print(f"Expected: ['E211', 'E319', 'E322', 'E500', 'E503']")