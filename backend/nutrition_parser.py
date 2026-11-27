import json
import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

# Reference names from the project's additive list, used for identification only;
# regulatory permission is decided by additive_regulatory_engine against FSSAI data.
_ADDITIVE_NAMES = {
    code: str(entry.get("name") or "")
    for code, entry in json.loads(
        (Path(__file__).with_name("data") / "additives.json").read_text(encoding="utf-8")
    ).items()
    if isinstance(entry, dict)
}


# Canonical nutrient names are kept compatible with the existing API.
NUTRIENT_PATTERNS = {
    "monounsaturated_fat": r"\bmonounsaturated\s+fat(?:ty\s+acids?)?\b",
    "polyunsaturated_fat": r"\bpolyunsaturated\s+fat(?:ty\s+acids?)?\b",
    "total_fat": r"\btotal\s+fat\b|(?<!saturated\s)(?<!trans\s)(?<!monounsaturated\s)(?<!polyunsaturated\s)\bfat\b",
    "saturated_fat": r"\bsaturated\s+fat(?:ty\s+acids?)?\b|\bsat\.?\s+fat\b|\bsaturates\b",
    "trans_fat": r"\btrans[\s\-]+fat(?:ty\s+acids?)?\b",
    "cholesterol": r"\bcholesterol\b",
    "sodium": r"\bsodium\b",
    # Indian labels often print bare "Carbohydrate" rather than "Total Carbohydrate".
    "total_carbohydrate": r"\btotal\s+carbohydrates?\b|\btotal\s+carbs?\b|\bcarbohydrates?\b|\bcarbs?\b",
    "dietary_fiber": r"\bdietary\s+fiber\b|\bdietary\s+fibre\b|\bfibre\b|\bfiber\b",
    "total_sugars": r"\btotal\s+sugars?\b|\bof\s+which\s+sugars?\b|\bsugars?\b",
    "added_sugars": r"\badded\s+sugars?\b",
    "protein": r"\bprotein\b",
    "calcium": r"\bcalcium\b",
    "iron": r"\biron\b",
    "potassium": r"\bpotassium\b",
}

NUTRIENT_UNITS = {
    "monounsaturated_fat": {"g"}, "polyunsaturated_fat": {"g"},
    "total_fat": {"g"}, "saturated_fat": {"g"}, "trans_fat": {"g"},
    "cholesterol": {"mg"}, "sodium": {"mg"},
    "total_carbohydrate": {"g"}, "dietary_fiber": {"g"},
    "total_sugars": {"g"}, "added_sugars": {"g"}, "protein": {"g"},
    "calcium": {"mg"}, "iron": {"mg"}, "potassium": {"mg"},
}

SUSPICIOUS_MAXIMUMS = {
    "monounsaturated_fat": 100.0, "polyunsaturated_fat": 100.0,
    "total_fat": 100.0, "saturated_fat": 100.0, "trans_fat": 100.0,
    "cholesterol": 5000.0, "sodium": 10000.0,
    "total_carbohydrate": 100.0, "dietary_fiber": 100.0,
    "total_sugars": 100.0, "added_sugars": 100.0, "protein": 100.0,
    "calcium": 2500.0, "iron": 100.0, "potassium": 10000.0,
}

ALLERGEN_TERMS = {
    "milk": (r"\bmilk\b", r"\bmilk\s+solids?\b", r"\bwhey\b", r"\bcasein(?:ate)?\b", r"\blactalbumin\b"),
    "egg": (r"\beggs?\b", r"\balbumen\b", r"\balbumin\b"),
    "wheat": (r"\bwheat\b", r"\bsemolina\b", r"\bspelt\b", r"\bfarina\b"),
    "gluten": (r"\bgluten\b", r"\bbarley\b", r"\brye\b", r"\bmalt(?:ed)?\b"),
    "soy": (r"\bsoy(?:bean)?s?\b", r"\bsoya\b", r"\bsoy\s+lecithin\b"),
    "peanut": (r"\bpeanuts?\b", r"\bgroundnuts?\b"),
    "tree_nuts": (r"\balmonds?\b", r"\bcashews?\b", r"\bwalnuts?\b", r"\bpistachios?\b", r"\bhazelnuts?\b", r"\bpine\s+nuts?\b", r"\bbrazil\s+nuts?\b"),
    "sesame": (r"\bsesame\b", r"\bgingelly\b", r"\btil\b"),
    "fish": (r"\bfish\b",),
    "crustaceans": (r"\bcrustaceans?\b", r"\bshrimp\b", r"\bprawns?\b", r"\bcrab\b", r"\blobster\b"),
    "molluscs": (r"\bmollus[ck]s?\b", r"\boysters?\b", r"\bclams?\b", r"\bmussels?\b", r"\bsquid\b", r"\boctopus\b"),
    "mustard": (r"\bmustard\b",),
    "celery": (r"\bcelery\b",),
    "lupin": (r"\blupin\b",),
    "sulphites": (r"\bsulphites?\b", r"\bsulfites?\b", r"\bsulphur\s+dioxide\b", r"\bsulfur\s+dioxide\b"),
}

UNIT_MAP = {
    "g": "g",
    "gm": "g",
    "gms": "g",
    "gram": "g",
    "grams": "g",
    "mg": "mg",
    "mcg": "mcg",
    "µg": "mcg",
    "ug": "mcg",
    "kcal": "kcal",
    "cal": "kcal",
    "calorie": "kcal",
    "calories": "kcal",
}

# Section labels that commonly terminate an ingredient/allergen block.
SECTION_STOP = (
    r"\b(?:allergens?|contains|may\s+contain|may\s+contain\s+traces\s+of|"
    r"nutrition(?:al)?\s+(?:information|facts|values?)|nutritional\s+information|"
    r"per\s+100\s*g|per\s+serving|storage|directions\s+for\s+use|"
    r"manufactured\s+by|marketed\s+by|best\s+before|batch\s*(?:no|number)?|"
    r"fssai|customer\s+care|net\s+quantity|serving\s+size|calories?|total\s+fat|saturated\s+fat|trans\s+fat|cholesterol|sodium|total\s+carbohydrate|total\s+carbs?|dietary\s+fiber|dietary\s+fibre|total\s+sugars?|added\s+sugars?|protein|calcium|iron|potassium)\b\s*:?"
)


def _clean(value: str) -> str:
    """Normalize whitespace while preserving meaningful word boundaries."""
    value = value.replace("\xa0", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\s*\n\s*", "\n", value)
    value = value.strip(" \t\r\n:;,")
    if value.startswith("-") and not re.match(r"-\s*\d", value):
        value = value.lstrip("-").lstrip()
    if value.endswith("-"):
        value = value.rstrip("-").rstrip()
    return value


def _number(value: str) -> float | None:
    try:
        return float(value.replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


_QUANTITY_PATTERN = re.compile(
    r"(?<![\w.])(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*(kcal|calories?|cal|gms?|grams?|g|mg|mcg|µg|ug)\b",
    flags=re.IGNORECASE,
)


def _split_pipe_cells(row: str) -> list[str]:
    """Split a pipe-delimited table row, stripping outer Markdown pipes."""
    stripped = row.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [_clean(cell) for cell in stripped.split("|")]


def _parse_quantity(
    text: str, *, column_index: int | None = None, default_unit: str | None = None
) -> dict[str, Any] | None:
    """Return the first number+unit; for tables, prefer the requested column.

    ``column_index`` is a pipe-table cell index. This keeps a per-100-g value
    from being read when a per-serving column appears first. Unknown basis is
    never coerced to zero.
    """
    match = None
    target = text
    if column_index is not None and "|" in text:
        cells = _split_pipe_cells(text)
        if 0 <= column_index < len(cells):
            target = cells[column_index]
            match = _QUANTITY_PATTERN.search(target)
    if match is None:
        match = _QUANTITY_PATTERN.search(text)
    if match is not None:
        value = _number(match.group(1))
        if value is None:
            return None
        raw_unit = match.group(2).lower()
        unit = "kcal" if raw_unit in {"cal", "calorie", "calories"} else UNIT_MAP.get(raw_unit, raw_unit)
        return {"value": value, "unit": unit}

    if default_unit:
        num_match = _NUMBER_PATTERN.search(target)
        value = _number(num_match.group(0)) if num_match else None
        if value is not None:
            return {"value": value, "unit": default_unit}
    return None


def _header_column(rows: list[str], pattern: str) -> int | None:
    """Find a table header cell index for `per 100` / `per serving`."""
    for row in rows:
        cells = _split_pipe_cells(row)
        for index, cell in enumerate(cells):
            if re.search(pattern, cell, re.IGNORECASE):
                return index
    return None


_KCAL_PATTERN = re.compile(
    r"(?<![\w.])(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*kcal\b",
    flags=re.IGNORECASE,
)
_KJ_PATTERN = re.compile(
    r"(?<![\w.])(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*kj\b",
    flags=re.IGNORECASE,
)
_NUMBER_PATTERN = re.compile(
    r"(?<![\w.])\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?",
    flags=re.IGNORECASE,
)


def _kcal_value(row: str, *, column_index: int | None = None) -> float | None:
    """Read kcal, preferring an explicit table column and converting kJ."""
    target = row
    restricted = False
    if column_index is not None and "|" in row:
        cells = _split_pipe_cells(row)
        if 0 <= column_index < len(cells):
            target = cells[column_index]
            restricted = True

    kcal_match = _KCAL_PATTERN.search(target)
    if kcal_match:
        return _number(kcal_match.group(1))
    kj_match = _KJ_PATTERN.search(target)
    if kj_match:
        kj = _number(kj_match.group(1))
        return round(kj / 4.184, 2) if kj is not None else None

    if restricted:
        match = _NUMBER_PATTERN.search(target)
    else:
        match = re.search(
            r"\b(?:calories?|energy)\b\s*[:|]?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)(?:\s*kcal)?",
            target,
            flags=re.IGNORECASE,
        )
    if not match:
        return None
    value = match.group(1) if match.lastindex else match.group(0)
    return _number(value)


def _row_nutrient(row: str) -> tuple[str | None, str]:
    """Identify a row's nutrient label without assigning unrelated quantities."""
    parts = _split_pipe_cells(row)
    label = parts[0] if len(parts) > 1 else row
    for key, pattern in NUTRIENT_PATTERNS.items():
        if re.search(pattern, label, re.IGNORECASE):
            if re.search(r"\badded\s+sugars?\b", label, re.IGNORECASE):
                key = "added_sugars"
            elif re.search(r"\btotal\s+sugars?\b", label, re.IGNORECASE):
                key = "total_sugars"
            return key, label
    return None, label


def _parse_serving_size(text: str) -> dict[str, Any] | None:
    for row in text.splitlines():
        match = re.search(r"\bserving\s+size\b\s*[:|]?\s*(.+)", row, flags=re.IGNORECASE)
        if not match:
            continue
        serving_text = _clean(re.split(
            r"\bamount\s+per\s+serving\b|\bcalories\b|\bdaily\s+value\b",
            match.group(1), maxsplit=1, flags=re.IGNORECASE
        )[0])
        if not serving_text:
            continue
        weight_match = re.search(
            r"(?<![\w.])([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*g\b",
            serving_text,
            flags=re.IGNORECASE,
        )
        weight_g = _number(weight_match.group(1)) if weight_match else None
        if weight_g is not None and weight_g <= 0:
            weight_g = None
        return {
            "text": serving_text,
            "weight_g": weight_g,
        }
    return None


def _extract_section(text: str, heading_pattern: str, stop_pattern: str = SECTION_STOP) -> str | None:
    """Extract a labelled section without consuming later label sections."""
    match = re.search(
        rf"(?is)(?:^|[\n|:]\s*)\s*(?:{heading_pattern})\s*:?\s*(.*?)(?={stop_pattern}|$)",
        text,
    )
    if not match:
        return None
    value = _clean(match.group(1))
    return value or None


def _allergen_matches(text: str) -> list[str]:
    found = []
    for allergen, patterns in ALLERGEN_TERMS.items():
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns):
            found.append(allergen)
    return found


def _extract_allergens(text: str, ingredients: str | None) -> dict[str, Any]:
    declared_text = _extract_section(text, r"allergens?(?!\s+information\b)")
    if declared_text is None:
        declared_text = _extract_section(text, r"contains")
    may_contain_text = _extract_section(
        text,
        r"may\s+contain(?:\s+traces\s+of)?",
        stop_pattern=r"\b(?:ingredients?|allergens?|contains|nutrition(?:al)?\s+(?:information|facts|values?)|storage|manufactured\s+by|marketed\s+by)\b\s*:?"
    )

    # Avoid treating a "Contains" heading inside a may-contain statement as a separate declaration.
    declared = _allergen_matches(declared_text or "")
    may_contain = _allergen_matches(may_contain_text or "")
    ingredient_detected = _allergen_matches(ingredients or "")

    if declared_text is not None or may_contain_text is not None:
        status = "declared_on_label"
    elif ingredients:
        status = "ingredient_terms_detected"
    else:
        status = "unknown"

    return {
        "declared": declared,
        "may_contain": may_contain,
        "ingredient_terms_detected": ingredient_detected,
        "declaration_text": declared_text,
        "precautionary_text": may_contain_text,
        "status": status,
        "review_required": status == "unknown" or declared_text is not None and not declared
                        or may_contain_text is not None and not may_contain,
    }


def _extract_additives(text: str | None, *, name_text: str | None = None, spaced_e: bool = True) -> list[str]:
    """Extract additive codes and names from OCR label text.

    ``text`` is scanned for E-numbers, INS codes, bracketed numbers and
    function-plus-number forms (the detection logic kept from the legacy
    parser, including comma/ampersand lists such as ``(503(ii), 500(ii))``).
    ``name_text`` is matched against the reference additive names, which only
    finds additives declared by name without a code. ``spaced_e=False`` is used
    for whole-text fallbacks so a nutrition row like "Vitamin E 100" is not
    read as additive E100.
    """
    combined = text or ""
    additives: set[str] = set()
    e_pattern = r"\b[eE][\s\-]?(\d{3,4}[a-z]?)\b" if spaced_e else r"\b[eE](\d{3,4}[a-z]?)\b"
    for num in re.findall(e_pattern, combined):
        additives.add(f"E{num.upper()}")
    for num, _ in re.findall(
        r"\bins[\s\-]?(\d{3,4})\s*\(?([a-z0-9]*)\)?", combined, re.IGNORECASE
    ):
        additives.add(f"E{num.upper()}")
    for num in re.findall(
        r"[\(\[\,&]\s*(\d{3,4})\s*(?:\([a-z0-9]+\))?\s*(?=[\)\]\,&]|$)", combined, re.IGNORECASE
    ):
        if 100 <= int(num) <= 1599:
            additives.add(f"E{num}")
    for num in re.findall(
        r"(?:raising agent|dough conditioner|emulsifier|preservative|stabiliser|"
        r"stabilizer|thickener|antioxidant|humectant|sequestrant|flavou?r enhancer|"
        r"bulking agent|colour|color|acidity regulator)s?\s*\[?\(?\s*(\d{3,4})",
        combined, re.IGNORECASE,
    ):
        if 100 <= int(num) <= 1599:
            additives.add(f"E{num}")

    # Do not treat arbitrary three- or four-digit values as additive codes. OCR
    # labels contain calories, pack weights and dates in the same range; codes
    # require an E/INS prefix, a bracketed ingredient-list context, or a
    # functional-class label above.

    # Reverse mapping: additive names to E-numbers (e.g., "sodium benzoate" → E211)
    lowered = (name_text or "").casefold()
    if lowered:
        name_to_code_map = {
            "sodium benzoate": "E211",
            "benzoic acid": "E211",
        }
        for name, code in name_to_code_map.items():
            if name.casefold() in lowered:
                additives.add(code)

    # Also check _ADDITIVE_NAMES reverse mapping (name → code without code in text)
    lowered = (name_text or "").casefold()
    if lowered:
        for code, name in _ADDITIVE_NAMES.items():
            base = re.sub(r"\s*\([^)]*\)", "", name).strip().casefold()
            if len(base) > 2 and re.search(rf"(?<!\w){re.escape(base)}s?(?!\w)", lowered):
                additives.add(code)
    return sorted(additives)


def _extract_ingredients(clean_text: str) -> str:
    """
    Extract complete multiline ingredients list.
    Handles single and multi-section ingredient labels (e.g., NOODLES + MASALA TASTEMAKER).
    Does NOT cut off at 'Contains' since 'Contains Wheat...' is an allergen note at the end of ingredients.
    """
    text = clean_text.strip()
    if not text:
        return "No ingredient list detected in label photo."

    # Look for explicit start markers (Ingredients, Composition, Noodles, Masala, Seasoning, Contents)
    start_pattern = r"(?:ingredients?|composition|contents?|noodles?|masala|tastemaker|seasoning|sauce|filling|crust)\s*[:：\-\s]"
    match_start = re.search(start_pattern, text, re.IGNORECASE)

    if match_start:
        start_idx = match_start.start()  # Keep header like "NOODLES:"
        remaining = text[start_idx:]
    else:
        # Check if text looks like purely a nutrition facts table without ingredients
        if re.search(r"nutrition\s+information|nutrition\s+facts|per\s+100g", text, re.IGNORECASE) and not re.search(r"flour|oil|salt|sugar|spices|water|protein|starch|additive", text, re.IGNORECASE):
            return "No ingredient list detected in label photo."
        remaining = text

    # Stop markers (commercial / mfg / regulatory details at the bottom)
    stop_pattern = r"(?:manufactured\s+by|marketed\s+by|mfg\s*\.?|net\s+wt|net\s+weight|batch\s+no|lic\s*\.?\s*no|fssai|store\s+in\s+a|for\s+feedback|customer\s+care|best\s+before|date\s+of\s+mfg)"
    match_stop = re.search(stop_pattern, remaining, re.IGNORECASE)

    if match_stop:
        ingredients_raw = remaining[:match_stop.start()]
    else:
        ingredients_raw = remaining

    # Clean up whitespace and linebreaks
    clean_ingredients = re.sub(r"\s+", " ", ingredients_raw).strip()
    return clean_ingredients if clean_ingredients else "No ingredient list detected in label photo."


def _to_text_and_rows(ocr_content: str) -> tuple[str, list[str]]:
    """Accept HTML, Markdown, or plain OCR text."""
    soup = BeautifulSoup(ocr_content or "", "html.parser")

    rows: list[str] = []
    for row in soup.find_all("tr"):
        cells = [_clean(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
        cells = [cell for cell in cells if cell]
        if cells:
            rows.append(" | ".join(cells))

    # Preserve line breaks in text-like OCR formats and strip common Markdown decoration.
    for br in soup.find_all(["br"]):
        br.replace_with("\n")
    text = soup.get_text("\n", strip=True)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"__(.*?)__", r"\1", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = text.replace("\r", "\n")
    # Sarvam sometimes joins adjacent label headings with no whitespace.
    text = re.sub(r"(?i)(?<=container)(?=serving\s+size)", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = _clean(text)

    if not rows:
        rows = [
            _clean(line)
            for line in text.splitlines()
            if _clean(line) and not re.fullmatch(r"[\s|:\-]+", line)
        ]
    return text, rows


def validate_food_label(label: Any) -> dict[str, Any]:
    """Fail closed on malformed parser output before it reaches NutriTrust scoring.

    This checks the in-code NutriTrust ``food_label`` shape; the downstream
    ``merge_product_data``/``product_analysis`` layer is the authoritative
    schema. Missing optional values stay ``None``; unknown is never coerced to 0.
    """
    if not isinstance(label, dict):
        raise ValueError("food label must be a JSON object")
    required = {
        "schema_version", "ingredients", "ingredient_items", "additives_tags",
        "product_name", "brand", "allergen_analysis", "serving_size",
        "calories_per_serving_kcal", "nutrition", "nutrition_review",
        "daily_values_percent", "raw_text", "extraction", "warnings",
    }
    missing = sorted(required - label.keys())
    if missing:
        raise ValueError(f"food label missing required fields: {', '.join(missing)}")
    if label["schema_version"] != "1.0":
        raise ValueError(f"unsupported food label schema_version: {label['schema_version']!r}")
    if not isinstance(label["nutrition"], dict):
        raise ValueError("nutrition must be an object keyed by canonical nutrient name")
    for nutrient, item in label["nutrition"].items():
        if not isinstance(item, dict) or not isinstance(item.get("value"), (int, float)) or isinstance(item.get("value"), bool):
            raise ValueError(f"nutrition.{nutrient} must contain a numeric value")
        if not isinstance(item.get("unit"), str) or not item["unit"]:
            raise ValueError(f"nutrition.{nutrient} must contain a unit")
    if not isinstance(label["allergen_analysis"], dict):
        raise ValueError("allergen_analysis must be an object")
    if not isinstance(label["ingredient_items"], list) or not isinstance(label["warnings"], list):
        raise ValueError("ingredient_items and warnings must be arrays")
    return label


def parse_food_label(ocr_content: str, *, ingredients_only: bool = False) -> dict[str, Any]:
    """Parse Sarvam OCR HTML/Markdown/plain text into structured food-label data.

    ``ingredients_only`` is used for a photo dedicated to the ingredients list,
    where the heading may be cropped out; it allows falling back to the full text.
    """
    if not isinstance(ocr_content, str) or not ocr_content.strip():
        return {
            "schema_version": "1.0",
            "ingredients": None,
            "ingredient_items": [],
            "additives_tags": [],
            "product_name": None,
            "brand": None,
            "allergens": None,
            "allergen_analysis": {
                "declared": [],
                "may_contain": [],
                "ingredient_terms_detected": [],
                "declaration_text": None,
                "precautionary_text": None,
                "status": "unknown",
                "review_required": True,
            },
            "servings_per_container": None,
            "serving_size": None,
            "calories_per_serving_kcal": None,
            "nutrition": {},
            "nutrition_review": [],
            "daily_values_percent": {},
            "raw_text": "",
            "extraction": {"status": "failed", "needs_review": True},
            "warnings": ["OCR returned no readable text."],
        }

    readable_text, rows = _to_text_and_rows(ocr_content)
    per_100g_column = _header_column(rows, r"(?:per\s*|/\s*)?100\s*(?:gms?|g|ml|grams?|milliliters?)\b")
    per_serving_column = _header_column(rows, r"per\s+serving|amount\s+per\s+serving")
    reference_basis = "unknown"
    if per_100g_column is not None:
        reference_basis = "per_100g"
    elif per_serving_column is not None:
        reference_basis = "per_serving"
    result: dict[str, Any] = {
        "schema_version": "1.0",
        "reference_basis": {"detected": reference_basis},
        "ingredients": None,
        "ingredient_items": [],
        "additives_tags": [],
        "product_name": None,
        "brand": None,
        "allergens": None,  # Legacy field retained for API compatibility.
        "allergen_analysis": {},
        "servings_per_container": None,
        "serving_size": None,
        "calories_per_serving_kcal": None,
        "nutrition": {},
        "nutrition_review": [],
        "daily_values_percent": {},
        "raw_text": readable_text,
        "extraction": {"status": "completed", "needs_review": False},
        "warnings": [],
    }

    for line in readable_text.splitlines():
        name_match = re.match(r"\s*(?:product\s+name|product)\s*:\s*(.+?)\s*$", line, re.IGNORECASE)
        if name_match and result["product_name"] is None:
            result["product_name"] = _clean(name_match.group(1)) or None
        brand_match = re.match(r"\s*brand\s*:\s*(.+?)\s*$", line, re.IGNORECASE)
        if brand_match and result["brand"] is None:
            result["brand"] = _clean(brand_match.group(1)) or None

    match = re.search(
        r"(?<![\w.])([+-]?\d+)\s+servings?\s+per\s+container\b",
        readable_text,
        re.IGNORECASE,
    )
    if match:
        count = int(match.group(1))
        if count > 0:
            result["servings_per_container"] = count
        else:
            result["warnings"].append("Servings per container must be a positive whole number.")

    result["serving_size"] = _parse_serving_size(readable_text)
    if result["serving_size"] and result["serving_size"]["weight_g"] is None:
        result["warnings"].append(
            "Serving size text was detected, but it does not contain a valid explicit weight in grams."
        )

    # Restrict nutrition scanning from the Nutrition header onward when present,
    # and skip the ingredients block so "sugar" in ingredients is not read as nutrition.
    nutrition_rows = rows
    for idx, row in enumerate(rows):
        if re.search(r"\bnutrition(?:al)?\s+(?:information|facts|values?)\b", row, re.IGNORECASE):
            nutrition_rows = rows[idx:]
            break
    else:
        nutrition_rows = [
            row for row in rows
            if not re.match(r"^\s*(?:ingredients?|composition|contains|may\s+contain)\b", row, re.IGNORECASE)
        ]

    header_unit_match = re.search(r"\(\s*(mg|mcg|g)\s*\)", " ".join(nutrition_rows[:3]), re.IGNORECASE)
    header_default_unit = UNIT_MAP.get(header_unit_match.group(1).lower()) if header_unit_match else None
    active_col = per_100g_column if per_100g_column is not None else per_serving_column

    for idx, row in enumerate(nutrition_rows):
        if re.search(r"\b(?:calories?|energy)\b", row, re.IGNORECASE):
            value = _kcal_value(row, column_index=active_col)
            if value is None and idx + 1 < len(nutrition_rows):
                value = _kcal_value(nutrition_rows[idx + 1], column_index=active_col)
            if value is not None:
                result["calories_per_serving_kcal"] = value
                break

    consumed_next: set[int] = set()
    for idx, row in enumerate(nutrition_rows):
        if idx in consumed_next:
            continue
        # Some labels list salt instead of sodium; convert using sodium = salt / 2.5.
        if (
            re.search(r"\bsalt\b", row, re.IGNORECASE)
            and "sodium" not in result["nutrition"]
        ):
            quantity = _parse_quantity(row, column_index=active_col, default_unit=header_default_unit)
            if quantity and quantity["unit"] in {"g", "mg"}:
                grams = quantity["value"] if quantity["unit"] == "g" else quantity["value"] / 1000
                sodium_mg = round(grams * 1000 / 2.5, 2)
                if 0 <= sodium_mg <= SUSPICIOUS_MAXIMUMS["sodium"]:
                    result["nutrition"]["sodium"] = {"value": sodium_mg, "unit": "mg"}
                    percent_match = re.search(r"(\d+(?:\.\d+)?)\s*%", row)
                    if percent_match:
                        result["daily_values_percent"]["sodium"] = _number(percent_match.group(1))
                    continue

        matched_key, label = _row_nutrient(row)
        if not matched_key:
            if re.search(r"(?<![\w.])\d+(?:\.\d+)?\s*(?:gms?|grams?|g|mg|mcg|µg|ug)\b", row, re.IGNORECASE):
                result["nutrition_review"].append({
                    "status": "unresolved", "row": row,
                    "reason": "A quantity was present without a confidently identified nutrient label.",
                })
            continue

        label_unit_match = re.search(r"\(\s*(mg|mcg|g)\s*\)", label, re.IGNORECASE)
        row_default_unit = (
            UNIT_MAP.get(label_unit_match.group(1).lower())
            if label_unit_match
            else header_default_unit
        )
        quantity = _parse_quantity(row, column_index=active_col, default_unit=row_default_unit)
        if quantity is None and idx + 1 < len(nutrition_rows):
            next_key, _ = _row_nutrient(nutrition_rows[idx + 1])
            if not next_key:
                quantity = _parse_quantity(
                    nutrition_rows[idx + 1], column_index=active_col, default_unit=row_default_unit
                )
                if quantity is not None:
                    consumed_next.add(idx + 1)
        if quantity is None:
            result["nutrition_review"].append({
                "status": "invalid", "nutrient": matched_key, "row": row,
                "reason": "No numeric amount with a recognized unit was found for the labelled nutrient.",
            })
            continue
        if quantity["unit"] not in NUTRIENT_UNITS[matched_key]:
            result["nutrition_review"].append({
                "status": "invalid", "nutrient": matched_key, "row": row,
                "value": quantity["value"], "unit": quantity["unit"],
                "reason": f"Unit {quantity['unit']} is incompatible with {matched_key}.",
            })
            continue

        reason = None
        maximum = SUSPICIOUS_MAXIMUMS[matched_key]
        if quantity["value"] > maximum:
            reason = f"Value exceeds the conservative plausibility review limit of {maximum:g} {quantity['unit']}."
        serving_weight = (result.get("serving_size") or {}).get("weight_g")
        if (
            reference_basis == "per_serving"
            and serving_weight
            and quantity["unit"] == "g"
            and quantity["value"] > serving_weight
        ):
            reason = f"Value exceeds the explicit serving mass of {serving_weight:g} g."
        if reason:
            result["nutrition_review"].append({
                "status": "suspicious", "nutrient": matched_key,
                "value": quantity["value"], "unit": quantity["unit"],
                "row": row, "reason": reason,
            })
            continue

        result["nutrition"][matched_key] = quantity

        percent_match = re.search(r"(\d+(?:\.\d+)?)\s*%", row)
        if percent_match:
            result["daily_values_percent"][matched_key] = _number(percent_match.group(1))

    # Ingredient extraction supports inline labels, Markdown, and a heading on its own line.
    ingredient_text = _extract_section(
        readable_text,
        r"(?:ingredients?(?:\s+list)?|composition|contents?|noodles?|masala|tastemaker|seasoning|sauce|filling|crust)",
        stop_pattern=r"\b(?:allergens?|contains|may\s+contain(?:\s+traces\s+of)?|nutrition(?:al)?\s+(?:information|facts|values?)|per\s+100\s*g|per\s+serving|storage|directions\s+for\s+use|manufactured\s+by|marketed\s+by|best\s+before|batch\s*(?:no|number)?|fssai|customer\s+care|net\s+quantity|serving\s+size)\b\s*:?"
    )
    if ingredient_text is None and ingredients_only:
        candidate = _clean(readable_text)
        if candidate and not re.search(
            r"\b(?:nutrition(?:al)?\s+(?:information|facts|values?)|per\s+100\s*g|calories?|"
            r"total\s+fat|saturated\s+fat|trans\s+fat|sodium|total\s+carbohydrate|protein)\b",
            candidate, re.IGNORECASE,
        ):
            ingredient_text = candidate
    if ingredient_text:
        ingredient_text = re.sub(r"^\s*[-*•]\s*", "", ingredient_text)
        ingredient_text = _clean(ingredient_text)
        result["ingredients"] = ingredient_text
        # Conservative split: preserve parenthetical sub-ingredients inside their parent item.
        result["ingredient_items"] = [
            _clean(item) for item in re.split(r"[;,](?![^()]*\))", ingredient_text)
            if _clean(item)
        ]

    # Codes are scanned from the ingredient list when it was extracted, otherwise
    # from the full OCR text (a cropped label may hide the heading); nutrition rows
    # alone rarely contain bracketed codes, and the E-number pattern needs an "E".
    result["additives_tags"] = _extract_additives(
        result["ingredients"] or readable_text,
        name_text=result["ingredients"],
        spaced_e=bool(result["ingredients"]),
    )
    result["allergen_analysis"] = _extract_allergens(readable_text, result["ingredients"])
    # Legacy string field remains available for clients that already expect a string.
    result["allergens"] = (
        result["allergen_analysis"]["declaration_text"]
        or result["allergen_analysis"]["precautionary_text"]
    )

    if result["ingredients"] is None:
        result["warnings"].append("Ingredient list not detected in the OCR output.")
    elif len(result["ingredients"]) < 5:
        result["warnings"].append("The extracted ingredient list is unusually short; verify it against the label.")

    if not result["nutrition"]:
        result["warnings"].append("No nutrition quantities could be parsed.")

    if result["nutrition_review"]:
        result["warnings"].append(
            "Some nutrition rows were invalid, suspicious, or unresolved; review the original label before using them."
        )

    if result["allergen_analysis"]["review_required"]:
        result["warnings"].append("Allergen information is missing or ambiguous; verify the original package label.")

    result["extraction"]["needs_review"] = bool(result["warnings"])
    if result["ingredients"] is None:
        result["extraction"]["status"] = "partial"

    return validate_food_label(result)
