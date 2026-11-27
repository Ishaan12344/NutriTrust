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

result = _extract_section(text, heading_pattern)
print(f"_extract_section result: '{result}'")
print(f"Length: {len(result) if result else 0}")

# Check what the regex actually matches
pattern = rf"(?is)(?:^|[\n|:]\s*)\s*(?:{heading_pattern})\s*:?\s*(.*?)(?=$)"
m = re.search(pattern, text)
if m:
    print(f"Full match: '{m.group(0)}'")
    print(f"Group 1: '{m.group(1)}'")