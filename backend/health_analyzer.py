"""Explainable product observations; this module deliberately does not score health."""
from __future__ import annotations

import math
import re
from typing import Any


RULESET = {
    "id": "uk_front_of_pack_food_thresholds",
    "version": "2016-guidance",
    "basis": "per_100g",
    "scope": "UK front-of-pack nutrient bands for foods; not a whole-product health rating",
    "threshold_source": "https://www.gov.uk/government/publications/front-of-pack-nutrition-labelling-guidance",
    "salt_conversion_source": "https://eur-lex.europa.eu/legal-content/EN/ALL/?uri=CELEX%3A32011R1169",
}

# Each threshold tuple is (low maximum, high begins above). Medium includes both
# endpoints of the interval between those values.
NUTRIENT_RULES: dict[str, dict[str, Any]] = {
    "sugar": {
        "label": "total sugars",
        "unit": "g",
        "low_max": 5.0,
        "high_above": 22.5,
        "rule_id": "uk_fop_total_sugars_per_100g",
    },
    "saturated_fat": {
        "label": "saturated fat",
        "unit": "g",
        "low_max": 1.5,
        "high_above": 5.0,
        "rule_id": "uk_fop_saturates_per_100g",
    },
    "sodium": {
        "label": "sodium (salt equivalent)",
        "unit": "mg",
        "low_max": 120.0,  # 0.3 g salt / 2.5 * 1000 mg/g
        "high_above": 600.0,  # 1.5 g salt / 2.5 * 1000 mg/g
        "rule_id": "uk_fop_salt_equivalent_sodium_per_100g",
    },
    "total_fat": {
        "label": "total fat",
        "unit": "g",
        "low_max": 3.0,
        "high_above": 17.5,
        "rule_id": "uk_fop_total_fat_per_100g",
    },
}

OBSERVATION_NUTRIENTS = {
    "monounsaturated_fat": ("monounsaturated fat", "g"),
    "polyunsaturated_fat": ("polyunsaturated fat", "g"),
    "fiber": ("dietary fiber", "g"),
    "protein": ("protein", "g"),
    "added_sugar": ("added sugars", "g"),
}


def _numeric_value(item: Any, expected_unit: str) -> tuple[float | None, str | None]:
    if not isinstance(item, dict) or item.get("value") is None:
        return None, "missing"
    value = item.get("value")
    if isinstance(value, bool):
        return None, "invalid"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None, "invalid"
    if not math.isfinite(number) or number < 0 or item.get("unit") != expected_unit:
        return None, "invalid"
    return number, None


def _source_for(nutrition: dict[str, Any], nutrient: str) -> str | None:
    item = nutrition.get(nutrient)
    return item.get("source") if isinstance(item, dict) else None


def _matching_conflict(conflicts: Any, nutrient: str) -> dict[str, Any] | None:
    if not isinstance(conflicts, list):
        return None
    return next(
        (item for item in conflicts if isinstance(item, dict) and item.get("nutrient") == nutrient),
        None,
    )


def _is_beverage(product: dict[str, Any]) -> bool:
    details = product.get("product") if isinstance(product.get("product"), dict) else {}
    categories = details.get("categories")
    text = " ".join(categories) if isinstance(categories, list) else str(categories or "")
    return bool(re.search(r"\b(beverages?|drinks?|juices?|soft drinks?)\b", text, re.IGNORECASE))


def _nutrient_finding(
    nutrient: str,
    item: Any,
    *,
    basis: str,
    conflicts: Any,
    label: str,
    unit: str,
    rule: dict[str, Any] | None,
) -> tuple[dict[str, Any], str | None]:
    conflict = _matching_conflict(conflicts, nutrient)
    value, invalid = _numeric_value(item, unit)
    source = _source_for({nutrient: item} if isinstance(item, dict) else {}, nutrient)
    measured = {"value": value, "unit": unit, "basis": basis, "source": source} if value is not None else None

    if conflict:
        finding = {
            "id": f"nutrition.{nutrient}",
            "type": "nutrient_threshold" if rule else "nutrient_observation",
            "status": "conflicting",
            "category": "conflicting_data",
            "severity": "review",
            "measured": measured,
            "applicable_rule": rule,
            "conflict": conflict,
            "explanation": "Sources report different values. The merged schema's selected value is shown, but no nutrient band is assigned until the conflict is reviewed.",
            "source": source or conflict.get("selected_source"),
        }
        return finding, "Conflicting nutrition data needs review."

    if invalid and invalid != "missing":
        finding = {
            "id": f"nutrition.{nutrient}",
            "type": "nutrient_threshold" if rule else "nutrient_observation",
            "status": "invalid",
            "category": "invalid_data",
            "severity": "review",
            "measured": item if isinstance(item, dict) else None,
            "applicable_rule": rule,
            "explanation": f"The {label} value is not a finite, non-negative number with the expected {unit} unit.",
            "source": source,
        }
        return finding, f"{label.capitalize()} data is invalid and was not assessed."

    if value is None:
        finding = {
            "id": f"nutrition.{nutrient}",
            "type": "nutrient_threshold" if rule else "nutrient_observation",
            "status": "missing",
            "category": "insufficient_data",
            "severity": "informational",
            "measured": None,
            "applicable_rule": rule,
            "explanation": f"No usable {label} value was available.",
            "source": None,
        }
        return finding, f"{label.capitalize()} data is missing."

    if basis != "per_100g" or rule is None:
        return {
            "id": f"nutrition.{nutrient}",
            "type": "nutrient_observation",
            "status": "known",
            "category": "reported_value",
            "severity": "informational",
            "measured": measured,
            "applicable_rule": rule,
            "explanation": (
                f"{label.capitalize()} is reported for {basis}; this rule has no validated threshold for that basis."
                if rule else f"{label.capitalize()} is reported as a measured value; no health threshold is applied by this analyzer."
            ),
            "source": source,
        }, (f"{label.capitalize()} is available only per serving; per-100-g bands were not applied." if rule and basis == "per_serving" else None)

    low_max = float(rule["low_max"])
    high_above = float(rule["high_above"])
    if value <= low_max:
        category, severity = "low", "informational"
        explanation = f"{value:g} {unit}/100 g is within the rule's low band (≤ {low_max:g} {unit}/100 g)."
    elif value > high_above:
        category, severity = "high", "attention"
        explanation = f"{value:g} {unit}/100 g is above the rule's high threshold (> {high_above:g} {unit}/100 g). This is a nutrient-level comparison, not a danger or whole-product health judgment."
    else:
        category, severity = "medium", "informational"
        explanation = f"{value:g} {unit}/100 g falls between the low and high cutoffs."

    return {
        "id": f"nutrition.{nutrient}",
        "type": "nutrient_threshold",
        "status": "known",
        "category": category,
        "severity": severity,
        "measured": measured,
        "applicable_rule": {
            "id": rule["rule_id"],
            "reference_basis": "per_100g",
            "unit": unit,
            "low_max": low_max,
            "high_above": high_above,
            "source": RULESET["threshold_source"],
            **({"conversion": "salt equivalent = sodium × 2.5"} if nutrient == "sodium" else {}),
        },
        "explanation": explanation,
        "source": source,
    }, None


def _classification_finding(
    identifier: str,
    label: str,
    value: Any,
    source: Any,
    *,
    valid,
    trust_source: bool,
) -> tuple[dict[str, Any], str | None]:
    finding_id = f"classification.{identifier}"
    if value is None or value == "":
        return ({
            "id": finding_id, "type": "classification", "status": "missing",
            "category": "not_supplied", "severity": "informational", "measured": None,
            "applicable_rule": None, "explanation": f"{label} was not supplied by the merged product data.", "source": None,
        }, f"{label} was not supplied.")
    if not trust_source or not valid(value):
        return ({
            "id": finding_id, "type": "classification", "status": "invalid",
            "category": "unverified_or_invalid", "severity": "review", "measured": value,
            "applicable_rule": None,
            "explanation": f"{label} is not a valid value from a source identified as Open Food Facts.",
            "source": source,
        }, f"{label} could not be verified and was not interpreted.")
    return ({
        "id": finding_id, "type": "classification", "status": "known",
        "category": "reported_classification", "severity": "informational", "measured": value,
        "applicable_rule": None,
        "explanation": f"{label} is reported by the identified Open Food Facts source; this analyzer does not recalculate it.",
        "source": source,
    }, None)


def analyze_product_health(merged_product: dict[str, Any] | None) -> dict[str, Any]:
    """Return transparent nutrient and label findings for ``merge_product_data`` output.

    This is an evidence summary, not medical advice, product-safety determination,
    regulatory compliance check, or overall health score.
    """
    product = merged_product if isinstance(merged_product, dict) else {}
    nutrition = product.get("nutrition") if isinstance(product.get("nutrition"), dict) else {}
    per_100g = nutrition.get("per_100g") if isinstance(nutrition.get("per_100g"), dict) else {}
    per_serving = nutrition.get("per_serving") if isinstance(nutrition.get("per_serving"), dict) else {}
    conflicts = nutrition.get("conflicts", [])
    beverage = _is_beverage(product)
    findings: list[dict[str, Any]] = []
    warnings: list[str] = []

    for nutrient, rule in NUTRIENT_RULES.items():
        item = per_100g.get(nutrient)
        basis = "per_100g"
        if item is None and nutrient in per_serving:
            item = per_serving[nutrient]
            basis = "per_serving"
        if beverage and basis == "per_100g":
            finding, warning = _nutrient_finding(
                nutrient, item, basis="per_100g", conflicts=conflicts,
                label=rule["label"], unit=rule["unit"], rule=None,
            )
            if finding["status"] == "known":
                finding["type"] = "nutrient_observation"
                finding["category"] = "not_assessed_product_basis"
                finding["explanation"] = "A beverage category was identified, but the selected UK beverage thresholds are per 100 ml and this value is per 100 g; no conversion or nutrient band was inferred."
            warning = "Beverage nutrient bands were not applied because per-100-ml values were unavailable."
        else:
            finding, warning = _nutrient_finding(
            nutrient, item, basis=basis, conflicts=conflicts,
            label=rule["label"], unit=rule["unit"], rule=rule,
            )
        findings.append(finding)
        if warning:
            warnings.append(warning)

    for nutrient, (label, unit) in OBSERVATION_NUTRIENTS.items():
        item = per_100g.get(nutrient)
        basis = "per_100g"
        if item is None and nutrient in per_serving:
            item = per_serving[nutrient]
            basis = "per_serving"
        finding, warning = _nutrient_finding(
            nutrient, item, basis=basis, conflicts=conflicts,
            label=label, unit=unit, rule=None,
        )
        findings.append(finding)
        if warning:
            warnings.append(warning)

    normalization = nutrition.get("ocr_normalization")
    normalization = normalization if isinstance(normalization, dict) else {}
    for issue in normalization.get("nutrition_review", []):
        if not isinstance(issue, dict):
            continue
        status = issue.get("status")
        status = status if status in {"invalid", "suspicious", "unresolved"} else "invalid"
        findings.append({
            "id": f"nutrition.review.{issue.get('nutrient') or 'unresolved'}",
            "type": "nutrition_extraction_review",
            "status": status,
            "category": "invalid_data" if status == "invalid" else "uncertain_extraction",
            "severity": "review",
            "measured": {
                "value": issue.get("value"),
                "unit": issue.get("unit"),
                "row": issue.get("row"),
            },
            "applicable_rule": None,
            "explanation": issue.get("reason") or "OCR nutrition row requires manual verification.",
            "source": "ocr_label",
        })
        warnings.append("One or more OCR nutrition rows require manual review.")

    ingredients = product.get("ingredients") if isinstance(product.get("ingredients"), dict) else {}
    ingredient_items = ingredients.get("items")
    ingredient_text = ingredients.get("text")
    ingredient_source = ingredients.get("source") or (product.get("data_sources") or {}).get("ingredient_items")
    if isinstance(ingredient_items, list) and ingredient_items:
        findings.append({
            "id": "ingredients.composition_and_order", "type": "ingredient_composition",
            "status": "known", "category": "label_observation", "severity": "informational",
            "measured": {"ordered_items": ingredient_items, "text": ingredient_text},
            "applicable_rule": None,
            "explanation": "Items are reported in the order extracted from the source list; no ingredient proportions or health effects are inferred.",
            "source": ingredient_source,
        })
    else:
        findings.append({
            "id": "ingredients.composition_and_order", "type": "ingredient_composition",
            "status": "missing", "category": "insufficient_data", "severity": "informational",
            "measured": {"ordered_items": [], "text": ingredient_text} if ingredient_text else None,
            "applicable_rule": None,
            "explanation": "A usable ordered ingredient list is not available.", "source": ingredient_source,
        })
        warnings.append("Ingredient composition or order could not be assessed.")

    allergens = product.get("allergens") if isinstance(product.get("allergens"), dict) else {}
    allergen_analysis = allergens.get("label_analysis") if isinstance(allergens.get("label_analysis"), dict) else {}
    declaration = allergens.get("declaration") or allergen_analysis.get("declaration_text")
    declared = allergens.get("declared") or allergen_analysis.get("declared") or []
    declaration_source = (product.get("data_sources") or {}).get("allergen_declaration")
    if declaration or declared:
        findings.append({
            "id": "allergens.label_declaration", "type": "allergen_declaration",
            "status": "known", "category": "label_observation", "severity": "review",
            "measured": {"declared": declared, "text": declaration}, "applicable_rule": None,
            "explanation": "Allergens explicitly reported in the label declaration are shown for user review; this is not an individualized allergy-safety determination.",
            "source": declaration_source or "ocr_label",
        })
    else:
        findings.append({
            "id": "allergens.label_declaration", "type": "allergen_declaration",
            "status": "missing", "category": "unknown", "severity": "review",
            "measured": None, "applicable_rule": None,
            "explanation": "No allergen declaration was identified. Missing declaration data does not mean allergen-free.",
            "source": None,
        })
        warnings.append("Allergen declaration is missing; the product must not be treated as allergen-free.")

    precautionary = allergens.get("precautionary_traces")
    if not isinstance(precautionary, dict):
        precautionary = {}
    trace_text = precautionary.get("text")
    trace_items = precautionary.get("allergens") or []
    trace_source = (product.get("data_sources") or {}).get("precautionary_traces")
    if trace_text or trace_items:
        findings.append({
            "id": "allergens.precautionary_traces", "type": "precautionary_allergen_statement",
            "status": "known", "category": "label_observation", "severity": "review",
            "measured": {"may_contain": trace_items, "text": trace_text}, "applicable_rule": None,
            "explanation": "Precautionary trace wording is reported separately from declared ingredients and allergens; it is not a quantitative contamination estimate.",
            "source": trace_source or "ocr_label",
        })
    else:
        findings.append({
            "id": "allergens.precautionary_traces", "type": "precautionary_allergen_statement",
            "status": "missing", "category": "unknown", "severity": "informational",
            "measured": None, "applicable_rule": None,
            "explanation": "No precautionary trace statement was identified; its absence does not establish absence of cross-contact.",
            "source": None,
        })
        warnings.append("Precautionary trace information is unavailable; cross-contact status is unknown.")

    off_tags = allergens.get("open_food_facts_tags") or []
    if off_tags:
        findings.append({
            "id": "allergens.open_food_facts_tags", "type": "database_allergen_tags",
            "status": "known", "category": "database_observation", "severity": "informational",
            "measured": off_tags, "applicable_rule": None,
            "explanation": "These are database tags and are kept distinct from the scanned package's allergen and precautionary declarations.",
            "source": (product.get("data_sources") or {}).get("allergen_database_tags") or "open_food_facts",
        })

    classification = product.get("classification") if isinstance(product.get("classification"), dict) else {}
    data_sources = product.get("data_sources") if isinstance(product.get("data_sources"), dict) else {}
    off_found = bool((product.get("open_food_facts") or {}).get("found"))
    trusted_nova = off_found and data_sources.get("nova_group") == "open_food_facts"
    nova = classification.get("nova_group")
    nova_finding, warning = _classification_finding(
        "nova_group", "NOVA group", nova,
        data_sources.get("nova_group"),
        valid=lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and float(v).is_integer() and 1 <= float(v) <= 4,
        trust_source=trusted_nova,
    )
    findings.append(nova_finding)
    if warning:
        warnings.append(warning)

    trusted_nutriscore = off_found and data_sources.get("nutriscore_grade") == "open_food_facts"
    grade = classification.get("nutriscore_grade")
    grade_finding, warning = _classification_finding(
        "nutriscore_grade", "Nutri-Score grade", grade,
        data_sources.get("nutriscore_grade"),
        valid=lambda v: isinstance(v, str) and v.lower() in {"a", "b", "c", "d", "e"},
        trust_source=trusted_nutriscore,
    )
    findings.append(grade_finding)
    if warning:
        warnings.append(warning)

    additive_tags = classification.get("additives_tags") or []
    additive_source = data_sources.get("additives")
    if additive_tags and additive_source == "open_food_facts":
        identified = [{"identifier": tag, "source": "open_food_facts"} for tag in additive_tags]
    else:
        identified = []
    for item in ingredient_items if isinstance(ingredient_items, list) else []:
        if isinstance(item, str):
            for match in re.finditer(r"\bE\s*\d{3,4}[A-Z]?\b", item, re.IGNORECASE):
                identifier = re.sub(r"\s+", "", match.group(0)).upper()
                if not any(additive["identifier"].upper() == identifier for additive in identified):
                    identified.append({"identifier": identifier, "source": ingredient_source or "ocr_label"})
    if identified:
        findings.append({
            "id": "ingredients.identified_additives", "type": "additive_identification",
            "status": "known", "category": "presence_observation", "severity": "informational",
            "measured": identified, "applicable_rule": None,
            "explanation": "Identifiers were found in source data. Presence alone is not evidence that an additive is dangerous or unsafe.",
            "source": "multiple" if len({item["source"] for item in identified}) > 1 else identified[0]["source"],
        })
    else:
        findings.append({
            "id": "ingredients.identified_additives", "type": "additive_identification",
            "status": "missing", "category": "not_identified", "severity": "informational",
            "measured": [], "applicable_rule": None,
            "explanation": "No additive identifiers were found in available database tags or explicit E-number ingredient text; this does not prove additives are absent.",
            "source": None,
        })
        warnings.append("Additive identification is incomplete or unavailable.")

    warnings = list(dict.fromkeys(warnings))
    return {
        "schema_version": "1.0",
        "analysis_status": "findings_available" if any(f["status"] == "known" for f in findings) else "insufficient_data",
        "overall_score": None,
        "overall_score_status": "not_calculated",
        "ruleset": RULESET,
        "findings": findings,
        "warnings": warnings,
        "needs_review": bool(warnings) or any(f["status"] in {"invalid", "conflicting"} for f in findings),
    }
