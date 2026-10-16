import re
from typing import Any

from bs4 import BeautifulSoup


# Canonical nutrient names are kept compatible with the existing API.
NUTRIENT_PATTERNS = {
    "monounsaturated_fat": r"\bmonounsaturated\s+fat\b",
    "polyunsaturated_fat": r"\bpolyunsaturated\s+fat\b",
    "total_fat": r"\btotal\s+fat\b",
    "saturated_fat": r"\bsaturated\s+fat\b",
    "trans_fat": r"\btrans\s+fat\b",
    "cholesterol": r"\bcholesterol\b",
    "sodium": r"\bsodium\b",
    "total_carbohydrate": r"\btotal\s+carbohydrate\b|\btotal\s+carbs?\b",
    "dietary_fiber": r"\bdietary\s+fiber\b|\bdietary\s+fibre\b|\bfibre\b|\bfiber\b",
    "total_sugars": r"\btotal\s+sugars?\b|\bsugars?\b",
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

UNIT_MAP = {
    "g": "g",
    "mg": "mg",
    "mcg": "mcg",
    "µg": "mcg",
    "ug": "mcg",
    "kcal": "kcal",
    "cal": "kcal",
    "calorie": "kcal",
    "calories": "kcal",
}

# These are useful for identifying text on labels, not a medical guarantee.
ALLERGEN_TERMS = {
    "milk": (r"\bmilk\b", r"\bmilk\s+solids?\b", r"\bwhey\b", r"\bcasein(?:ate)?\b", r"\blactalbumin\b"),
    "egg": (r"\beggs?\b", r"\balbumen\b", r"\balbumin\b"),
    "wheat": (r"\bwheat\b", r"\bsemolina\b", r"\bspelt\b", r"\bfarina\b"),
    "gluten": (r"\bgluten\b", r"\bbarley\b", r"\brye\b", r"\bmalt(?:ed)?\b"),
    "soy": (r"\bsoy(?:bean)?s?\b", r"\bsoya\b", r"\bsoy\s+lecithin\b"),
    "peanut": (r"\bpeanuts?\b", r"\bgroundnuts?\b"),
    "tree_nuts": (r"\balmonds?\b", r"\bcashews?\b", r"\bwalnuts?\b", r"\bpistachios?\b", r"\bhazelnuts?\b", r"\bpecans?\b", r"\bmacadamias?\b", r"\bpine\s+nuts?\b", r"\bbrazil\s+nuts?\b"),
    "sesame": (r"\bsesame\b", r"\bgingelly\b", r"\btil\b"),
    "fish": (r"\bfish\b",),
    "crustaceans": (r"\bcrustaceans?\b", r"\bshrimp\b", r"\bprawns?\b", r"\bcrab\b", r"\blobster\b"),
    "molluscs": (r"\bmollus[ck]s?\b", r"\boysters?\b", r"\bclams?\b", r"\bmussels?\b", r"\bsquid\b", r"\boctopus\b"),
    "mustard": (r"\bmustard\b",),
    "celery": (r"\bcelery\b",),
    "lupin": (r"\blupin\b",),
    "sulphites": (r"\bsulphites?\b", r"\bsulfites?\b", r"\bsulphur\s+dioxide\b", r"\bsulfur\s+dioxide\b"),
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


def _parse_quantity(text: str) -> dict[str, Any] | None:
    match = re.search(
        r"(?<![\w.])(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*"
        r"(kcal|calories?|cal|g|mg|mcg|µg|ug)\b",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    value = _number(match.group(1))
    if value is None:
        return None

    raw_unit = match.group(2).lower()
    unit = "kcal" if raw_unit in {"cal", "calorie", "calories"} else UNIT_MAP.get(raw_unit, raw_unit)
    return {"value": value, "unit": unit}


def _row_nutrient(row: str) -> tuple[str | None, str]:
    """Identify a row's nutrient label without assigning unrelated quantities."""
    parts = [_clean(part) for part in row.split("|")]
    label = parts[0] if len(parts) > 1 else row
    for key, pattern in NUTRIENT_PATTERNS.items():
        if re.search(pattern, label, re.IGNORECASE):
            if re.search(r"\badded\s+sugars?\b", label, re.IGNORECASE):
                key = "added_sugars"
            elif re.search(r"\btotal\s+sugars?\b", label, re.IGNORECASE):
                key = "total_sugars"
            return key, label
    return None, label


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
        rows = [_clean(line) for line in text.splitlines() if _clean(line)]
    return text, rows


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
    # Avoid returning just punctuation or a repeated heading.
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


def parse_food_label(ocr_content: str) -> dict[str, Any]:
    """Parse Sarvam OCR HTML/Markdown/plain text into structured food-label data."""
    if not isinstance(ocr_content, str) or not ocr_content.strip():
        return {
            "ingredients": None,
            "ingredient_items": [],
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
    combined_rows = "\n".join(rows)
    result: dict[str, Any] = {
        "ingredients": None,
        "ingredient_items": [],
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

    for row in rows:
        if re.search(r"\b(?:calories?|energy)\b", row, re.IGNORECASE):
            match = re.search(
                r"\b(?:calories?|energy)\b\s*[:|]?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)(?:\s*kcal)?",
                row, flags=re.IGNORECASE
            )
            if match:
                result["calories_per_serving_kcal"] = _number(match.group(1))
                break

    for row in rows:
        matched_key, label = _row_nutrient(row)
        if not matched_key:
            if re.search(r"(?<![\w.])\d+(?:\.\d+)?\s*(?:g|mg|mcg|µg|ug)\b", row, re.IGNORECASE):
                result["nutrition_review"].append({
                    "status": "unresolved", "row": row,
                    "reason": "A quantity was present without a confidently identified nutrient label.",
                })
            continue

        quantity = _parse_quantity(row)
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
        if serving_weight and quantity["unit"] == "g" and quantity["value"] > serving_weight:
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
        r"ingredients?(?:\s+list)?",
        stop_pattern=r"\b(?:allergens?|contains|may\s+contain(?:\s+traces\s+of)?|nutrition(?:al)?\s+(?:information|facts|values?)|per\s+100\s*g|per\s+serving|storage|directions\s+for\s+use|manufactured\s+by|marketed\s+by|best\s+before|batch\s*(?:no|number)?|fssai|customer\s+care|net\s+quantity|serving\s+size|calories?|total\s+fat|saturated\s+fat|trans\s+fat|cholesterol|sodium|total\s+carbohydrate|total\s+carbs?|dietary\s+fiber|dietary\s+fibre|total\s+sugars?|added\s+sugars?|protein|calcium|iron|potassium)\b\s*:?"
    )
    if ingredient_text:
        ingredient_text = re.sub(r"^\s*[-*•]\s*", "", ingredient_text)
        ingredient_text = _clean(ingredient_text)
        result["ingredients"] = ingredient_text
        # Conservative split: preserve parenthetical sub-ingredients inside their parent item.
        result["ingredient_items"] = [
            _clean(item) for item in re.split(r"[;,](?![^()]*\))", ingredient_text)
            if _clean(item)
        ]

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

    return result
