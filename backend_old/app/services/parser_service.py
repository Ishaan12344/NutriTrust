"""
Parser Service — Enhanced & Accurate
Parses raw OCR text output (including HTML/Markdown tables from Sarvam AI) into structured nutrition data.
Fixes:
  1. Parses HTML (<table>) and Markdown (|...|) tables into clean label-value pairs.
  2. Strips raw HTML/Markdown tags to clean text so regexes work seamlessly.
  3. Distinguishes missing values (None) from 0.0.
  4. Extracts full multiline ingredient lists without leaking raw HTML tags.
  5. Parses bracketed INS additive codes like [503(ii), 341(ii), 500(ii) & 450(i)], (223).
"""

import re
from html.parser import HTMLParser


class TableHTMLParser(HTMLParser):
    """Parses HTML tables into rows of text cells."""
    def __init__(self):
        super().__init__()
        self.rows = []
        self.current_row = []
        self.current_cell = []
        self.in_cell = False

    def handle_starttag(self, tag, attrs):
        if tag in ("td", "th"):
            self.in_cell = True
            self.current_cell = []
        elif tag == "tr":
            self.current_row = []

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self.in_cell = False
            cell_text = "".join(self.current_cell).strip()
            self.current_row.append(cell_text)
        elif tag == "tr":
            if self.current_row:
                # Filter out completely empty cells
                cleaned = [c for c in self.current_row if c]
                if cleaned:
                    self.rows.append(cleaned)

    def handle_data(self, data):
        if self.in_cell:
            self.current_cell.append(data)


def _strip_html_and_markdown(raw_text: str) -> str:
    """Convert HTML tables/tags and Markdown table syntax into clean text lines."""
    text = raw_text

    # Replace HTML breaks/paragraphs/rows with linebreaks
    text = re.sub(r"<(?:br|p|tr|div|/tr|/p|/div)[^>]*>", "\n", text, flags=re.IGNORECASE)
    # Replace table headers/cells with colon/tab separators
    text = re.sub(r"</(?:td|th)>", " : ", text, flags=re.IGNORECASE)
    # Strip remaining HTML tags
    text = re.sub(r"<[^>]+>", " ", text)

    # Process line by line
    clean_lines = []
    for line in text.splitlines():
        line_str = line.strip()
        if not line_str:
            continue
        # Clean markdown table pipes: | Energy (kcal) | 384 | -> Energy (kcal) : 384
        if "|" in line_str:
            parts = [p.strip() for p in line_str.split("|") if p.strip()]
            # Skip separator lines like |---|---|
            if all(re.match(r"^[\:\-\s]+$", p) for p in parts):
                continue
            line_str = " : ".join(parts)

        # Normalize multiple spaces/colons
        line_str = re.sub(r"\s*:\s*", ": ", line_str)
        line_str = re.sub(r"\s+", " ", line_str).strip()
        clean_lines.append(line_str)

    return "\n".join(clean_lines)


def _extract_table_rows(raw_text: str) -> list[tuple[str, str]]:
    """Extract key-value pairs (label, value) from HTML tables, Markdown tables, or colon lines."""
    rows = []

    # 1. Try HTML Table Parsing
    if "<table" in raw_text.lower() or "<tr" in raw_text.lower():
        try:
            parser = TableHTMLParser()
            parser.feed(raw_text)
            for row in parser.rows:
                if len(row) >= 2:
                    label = row[0].strip()
                    # Use the first numeric-like column as value (per 100g usually comes first)
                    val = row[1].strip()
                    rows.append((label, val))
        except Exception:
            pass

    # 2. Try Markdown / Colon line parsing from cleaned text
    clean_text = _strip_html_and_markdown(raw_text)
    for line in clean_text.splitlines():
        if ":" in line:
            parts = line.split(":", 1)
            label = parts[0].strip()
            val = parts[1].strip()
            if label and val:
                rows.append((label, val))
        elif " " in line:
            # Match lines like "Energy 384 kcal" or "Total Fat 12.5g"
            match = re.match(r"^([A-Za-z\s\-\(\)\^\*]+)\s+([\d\.]+\s*(?:g|mg|kcal|cal|kj)?)$", line.strip(), re.IGNORECASE)
            if match:
                rows.append((match.group(1).strip(), match.group(2).strip()))

    return rows


def parse(ocr_result: dict) -> dict:
    """
    Parse OCR-extracted text into structured nutrition data.
    Handles raw text, HTML tables, and Markdown tables from Sarvam AI OCR.
    """
    raw_text = ocr_result.get("combined_text", "")
    clean_text = _strip_html_and_markdown(raw_text)
    text_lower = clean_text.lower()

    table_rows = _extract_table_rows(raw_text)

    # Primary extraction via regex on clean text
    nutrition = {
        "energy_kcal": _extract_nutrient(text_lower, table_rows, "energy", ENERGY_PATTERNS),
        "total_fat": _extract_nutrient(text_lower, table_rows, "total_fat", FAT_PATTERNS),
        "saturated_fat": _extract_nutrient(text_lower, table_rows, "saturated_fat", SAT_FAT_PATTERNS),
        "trans_fat": _extract_nutrient(text_lower, table_rows, "trans_fat", TRANS_FAT_PATTERNS),
        "sugar": _extract_nutrient(text_lower, table_rows, "sugar", SUGAR_PATTERNS),
        "sodium": _extract_sodium(text_lower, table_rows),
        "fiber": _extract_nutrient(text_lower, table_rows, "fiber", FIBER_PATTERNS),
        "protein": _extract_nutrient(text_lower, table_rows, "protein", PROTEIN_PATTERNS),
    }

    # Extract ingredients text
    ingredients = _extract_ingredients(clean_text)

    # Extract additives from text (E-numbers, INS codes, bracketed codes like [503(ii), 341(ii), 500(ii) & 450(i)], (223))
    additives = _extract_additives(text_lower, ingredients.lower())

    # Product name
    lines = [l.strip() for l in clean_text.split("\n") if l.strip()]
    product_name = lines[0] if lines else "Unknown Product (OCR)"
    # Clean product name if it's a table header
    if re.search(r"nutrition|information|per 100g|facts", product_name, re.IGNORECASE):
        product_name = "Scanned Food Product"

    return {
        "product": {
            "name": product_name,
            "brand": "Unknown (from OCR)",
            "barcode": None,
            "categories": "",
            "image_url": "",
            "source": "ocr",
        },
        "nutrition_per_100g": nutrition,
        "ingredients_text": ingredients,
        "additives_tags": additives,
        "nova_group": None,
        "ocr_raw": ocr_result,
    }


def parse_dual(ocr_nutrition: dict | None, ocr_ingredients: dict | None) -> dict:
    """
    Parse up to two separate OCR outputs (one from Nutrition Facts label photo, one from Ingredients list photo).
    Handles cases where only one or both images are provided.
    """
    if ocr_nutrition and not ocr_ingredients:
        return parse(ocr_nutrition)

    if ocr_ingredients and not ocr_nutrition:
        return parse(ocr_ingredients)

    if not ocr_nutrition and not ocr_ingredients:
        raise ValueError("Neither nutrition nor ingredients OCR data was provided.")

    # Both provided!
    parsed_nutr = parse(ocr_nutrition)
    parsed_ingr = parse(ocr_ingredients)

    # Combine nutrition facts: primary from nutrition image, fallback to ingredients image
    combined_nutrition = parsed_nutr["nutrition_per_100g"].copy()
    for key, val in parsed_ingr["nutrition_per_100g"].items():
        if combined_nutrition.get(key) is None and val is not None:
            combined_nutrition[key] = val

    # Use ingredients text from ingredients image if valid, else fallback to nutrition image
    ingr_text = parsed_ingr["ingredients_text"]
    if not ingr_text or ingr_text == "No ingredient list detected in label photo.":
        ingr_text = parsed_nutr["ingredients_text"]

    # Combine additives from both images
    combined_additives = sorted(list(set(parsed_nutr["additives_tags"] + parsed_ingr["additives_tags"])))

    # Choose product name
    prod_name = parsed_nutr["product"]["name"]
    if prod_name in ["Scanned Food Product", "Unknown Product (OCR)"]:
        if parsed_ingr["product"]["name"] not in ["Scanned Food Product", "Unknown Product (OCR)"]:
            prod_name = parsed_ingr["product"]["name"]

    combined_ocr_raw = {
        "nutrition_ocr": ocr_nutrition,
        "ingredients_ocr": ocr_ingredients,
    }

    return {
        "product": {
            "name": prod_name,
            "brand": "Unknown (from Dual OCR)",
            "barcode": None,
            "categories": "",
            "image_url": "",
            "source": "ocr_dual",
        },
        "nutrition_per_100g": combined_nutrition,
        "ingredients_text": ingr_text,
        "additives_tags": combined_additives,
        "nova_group": None,
        "ocr_raw": combined_ocr_raw,
    }


# ─────────────────────────────────────────────
# Regex Patterns & Table Row Parsing
# ─────────────────────────────────────────────

ENERGY_PATTERNS = [
    r"energy[:\s]*(\d+\.?\d*)\s*kcal",
    r"energy\s*\([^\)]*\)[:\s]*(\d+\.?\d*)",
    r"energy[:\s]*(\d+\.?\d*)",
    r"calories[:\s]*(\d+\.?\d*)",
    r"calorific\s+value[:\s]*(\d+\.?\d*)",
    r"energy\s+value[:\s]*(\d+\.?\d*)",
    r"(\d+\.?\d*)\s*kcal",
]

FAT_PATTERNS = [
    r"total\s+fat[:\s]*(\d+\.?\d*)",
    r"(?<!saturated\s)(?<!trans\s)fat[:\s]*(\d+\.?\d*)\s*g",
    r"(?<!saturated\s)(?<!trans\s)fat[:\s]*(\d+\.?\d*)",
]

SAT_FAT_PATTERNS = [
    r"saturated\s+fatty\s+acids?[:\s]*(\d+\.?\d*)",
    r"saturated\s+fat[^\d\n]*[:\s]*(\d+\.?\d*)",
    r"saturated\s+fats?[:\s]*(\d+\.?\d*)",
    r"sat[\.\s]+fat[:\s]*(\d+\.?\d*)",
    r"saturates[:\s]*(\d+\.?\d*)",
    r"saturated[:\s]*(\d+\.?\d*)",
]

TRANS_FAT_PATTERNS = [
    r"trans\s+fatty\s+acids?[:\s]*(\d+\.?\d*)",
    r"trans\s+fat[^\d\n]*[:\s]*(\d+\.?\d*)",
    r"trans[\-\s]+fat[:\s]*(\d+\.?\d*)",
]

SUGAR_PATTERNS = [
    r"total\s+sugar[s]?[:\s]*(\d+\.?\d*)",
    r"sugar[s]?[:\s]*(\d+\.?\d*)",
    r"added\s+sugar[s]?[:\s]*(\d+\.?\d*)",
    r"of\s+which\s+sugar[s]?[:\s]*(\d+\.?\d*)",
]

SODIUM_PATTERNS = [
    r"sodium[:\s]*(\d+\.?\d*)\s*mg",
    r"sodium[:\s]*(\d+\.?\d*)\s*g",
    r"sodium[:\s]*(\d+\.?\d*)",
]

SALT_PATTERNS = [
    r"salt[:\s]*(\d+\.?\d*)\s*g",
    r"salt[:\s]*(\d+\.?\d*)\s*mg",
    r"salt[:\s]*(\d+\.?\d*)",
]

FIBER_PATTERNS = [
    r"dietary\s+fib[re]+[:\s]*(\d+\.?\d*)",
    r"fib[re]+[:\s]*(\d+\.?\d*)",
]

PROTEIN_PATTERNS = [
    r"protein[s]?[:\s]*(\d+\.?\d*)",
    r"protein[s]?\s+(\d+\.?\d*)",
]


def _extract_nutrient(text: str, table_rows: list[tuple[str, str]], nutrient_type: str, patterns: list) -> float | None:
    """Try regex patterns on text first; fallback to structured table row searching."""
    # 1. Try regex on cleaned text
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                val = float(match.group(1))
                return round(val, 2)
            except (ValueError, IndexError):
                continue

    # 2. Try matching structured table rows
    for label, val in table_rows:
        label_lower = label.lower()
        # Check nutrient type match in label
        match_found = False
        if nutrient_type == "energy" and any(k in label_lower for k in ["energy", "kcal", "calories"]):
            match_found = True
        elif nutrient_type == "total_fat" and "fat" in label_lower and "sat" not in label_lower and "trans" not in label_lower:
            match_found = True
        elif nutrient_type == "saturated_fat" and ("saturated" in label_lower or "sat fat" in label_lower):
            match_found = True
        elif nutrient_type == "trans_fat" and "trans" in label_lower:
            match_found = True
        elif nutrient_type == "sugar" and ("total sugar" in label_lower or "sugar" in label_lower):
            match_found = True
        elif nutrient_type == "protein" and "protein" in label_lower:
            match_found = True
        elif nutrient_type == "fiber" and ("fiber" in label_lower or "fibre" in label_lower):
            match_found = True

        if match_found:
            # Extract number from val or label+val
            num_match = re.search(r"(\d+\.?\d*)", val)
            if num_match:
                try:
                    return round(float(num_match.group(1)), 2)
                except ValueError:
                    pass

    return None


def _extract_sodium(text: str, table_rows: list[tuple[str, str]]) -> float | None:
    """Extract sodium in mg. Converts salt -> sodium if sodium not present directly."""
    for pattern in SODIUM_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                val = float(match.group(1))
                if "g" in pattern and "mg" not in pattern:
                    val = val * 1000
                return round(val, 2)
            except (ValueError, IndexError):
                continue

    # Search table rows for sodium or salt
    for label, val in table_rows:
        label_lower = label.lower()
        if "sodium" in label_lower or "salt" in label_lower:
            num_match = re.search(r"(\d+\.?\d*)", val)
            if num_match:
                try:
                    num_val = float(num_match.group(1))
                    if "salt" in label_lower:
                        num_val = num_val / 2.5 if num_val < 100 else (num_val / 1000) / 2.5
                    elif "g" in val.lower() and "mg" not in val.lower() and num_val < 50:
                        num_val = num_val * 1000
                    return round(num_val, 2)
                except ValueError:
                    pass

    for pattern in SALT_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                salt_val = float(match.group(1))
                if "g" in pattern and "mg" not in pattern:
                    salt_val = salt_val * 1000
                sodium = salt_val / 2.5
                return round(sodium, 2)
            except (ValueError, IndexError):
                continue

    return None


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
    stop_pattern = r"(?:manufactured\s+by|marketed\s+by|mfg\s*\.?|net\s+wt|net\s+weight|batch\s+no|lic\s*\.?\s*no|fssai|store\s+in\s+a|for\s+feedback|customer\s+care|best\s+before|date\ of\ mfg)"
    match_stop = re.search(stop_pattern, remaining, re.IGNORECASE)

    if match_stop:
        ingredients_raw = remaining[:match_stop.start()]
    else:
        ingredients_raw = remaining

    # Clean up whitespace and linebreaks
    clean_ingredients = re.sub(r"\s+", " ", ingredients_raw).strip()
    return clean_ingredients if clean_ingredients else "No ingredient list detected in label photo."


def _extract_additives(full_text: str, ingredients_text: str) -> list:
    """
    Extract E-numbers, INS codes, and bracketed numbers like [503(ii), 341(ii), 500(ii) & 450(i)], (223).
    """
    additives = set()
    combined = full_text + " " + ingredients_text

    # 1. Standard E-numbers: E100, E621, E211, E500
    e_matches = re.findall(r"\b[eE][\s\-]?(\d{3,4}[a-z]?)\b", combined)
    for num in e_matches:
        additives.add(f"E{num.upper()}")

    # 2. Standard INS numbers: INS 621, INS 503(ii), INS500ii
    ins_matches = re.findall(r"\bins[\s\-]?(\d{3,4})\s*\(?([a-z0-9]*)\)?", combined, re.IGNORECASE)
    for num, sub in ins_matches:
        additives.add(f"E{num.upper()}")

    # 3. Bracketed / Parenthesized additive numbers in ingredients: [503(ii), 341(ii), 500(ii), 450(i)], (223)
    bracketed_matches = re.findall(r"[\(\[\,]\s*(\d{3,4})\s*(?:\([a-z0-9]+\))?\s*[\)\]\,]", combined)
    for num in bracketed_matches:
        # Avoid matching years or calorie numbers by checking range (additives are 100 to 1599)
        if 100 <= int(num) <= 1599:
            additives.add(f"E{num}")

    # 4. Keyword search for raising agents / conditioners with trailing numbers
    keyword_numbers = re.findall(r"(?:raising agent|dough conditioner|emulsifier|preservative|stabiliser|colour|color|acidity regulator)\s*s?\s*\[?\s*(\d{3,4})", combined, re.IGNORECASE)
    for num in keyword_numbers:
        if 100 <= int(num) <= 1599:
            additives.add(f"E{num}")

    return sorted(list(additives))
