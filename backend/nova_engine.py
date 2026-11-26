"""Explainable, rule-based NOVA classification from ingredient information.

Rules and their limits are documented in ``FOOD_INTELLIGENCE_REFERENCES.md``.
The engine returns evidence and uncertainty instead of a calibrated numeric
confidence, which would be scientifically unjustified for label-level rules.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

GROUP_NAMES = {
    1: "Unprocessed or minimally processed foods",
    2: "Processed culinary ingredients",
    3: "Processed foods",
    4: "Ultra-processed foods",
}

_RULES_PATH = Path(__file__).with_name("data") / "nova_rules.json"
# shortcut: marker lists are a practical subset, not a complete NOVA lexicon; upgrade from official label studies when needed.
_RULES = json.loads(_RULES_PATH.read_text(encoding="utf-8"))


def _matches(text: str, terms: list[str]) -> list[str]:
    found = []
    for term in terms:
        pattern = r"(?<!\w)" + re.escape(term) + r"(?!\w)"
        if re.search(pattern, text) and term not in found:
            found.append(term)
    return found


def _ingredient_text(data: dict[str, Any]) -> str:
    text = data.get("ingredients_text")
    if isinstance(text, str) and text.strip():
        return " ".join(text.casefold().split())
    items = data.get("ingredient_items")
    if isinstance(items, list):
        joined = ", ".join(str(item) for item in items if isinstance(item, str) and item.strip())
        if joined:
            return " ".join(joined.casefold().split())
    return ""


def _supporting_items(data: dict[str, Any], markers: list[str]) -> list[str]:
    raw_items = data.get("ingredient_items")
    items = (
        [str(item) for item in raw_items if isinstance(item, str) and item.strip()]
        if isinstance(raw_items, list) else []
    )
    if not items and isinstance(data.get("ingredients_text"), str):
        items = [part.strip() for part in re.split(r"[,;]", data["ingredients_text"]) if part.strip()]
    return [item for item in items if any(marker in item.casefold() for marker in markers)]


def classify_nova(data: dict[str, Any]) -> dict[str, Any]:
    """Classify a product into NOVA groups 1-4 with explicit supporting evidence."""
    data = data if isinstance(data, dict) else {}
    text = _ingredient_text(data)
    external_group = data.get("nova_group")
    external_source = data.get("nova_source")
    external_valid = (
        isinstance(external_group, (int, float))
        and not isinstance(external_group, bool)
        and float(external_group).is_integer()
        and int(external_group) in GROUP_NAMES
    )
    if external_valid:
        external_group = int(external_group)
    external = {
        "nova_group": external_group if external_valid else None,
        "source": external_source if external_valid else None,
        "agrees_with_rules": None,
    }

    result: dict[str, Any] = {
        "group": None,
        "group_name": None,
        "status": "undetermined",
        "reasons": [],
        "supporting_ingredients": [],
        "processing_indicators": [],
        "uncertainty": None,
        "missing_information": [],
        "evidence_strength": "none",
        "external_classification": external,
        "framework": "NOVA 2017 four-group framework; 2019 practical marker rule",
    }

    if not text:
        result["missing_information"].append("ingredient list")
        result["uncertainty"] = "NOVA group cannot be determined without an ingredient list."
        if external_valid:
            result["group"] = external_group
            result["group_name"] = GROUP_NAMES[external_group]
            result["status"] = "external_source"
            result["reasons"].append(
                f"NOVA group {external_group} was supplied by {external_source or 'an external source'}; "
                "ingredient-level verification was not possible."
            )
            result["evidence_strength"] = "external_source"
        result["external_classification"]["agrees_with_rules"] = None
        return result

    non_culinary = _matches(text, _RULES["g4_non_culinary_terms"])
    cosmetic = _matches(text, _RULES["g4_cosmetic_terms"])
    ambiguous = _matches(text, _RULES["ambiguous_terms"])
    group1 = _matches(text, _RULES["group1_terms"])
    group2 = _matches(text, _RULES["group2_terms"])
    group3 = _matches(text, _RULES["group3_terms"])

    g4_markers = list(dict.fromkeys(non_culinary + cosmetic))
    result["processing_indicators"] = list(dict.fromkeys(non_culinary + cosmetic + group3 + ambiguous))
    if g4_markers:
        result["group"] = 4
        result["group_name"] = GROUP_NAMES[4]
        result["status"] = "classified"
        result["supporting_ingredients"] = _supporting_items(data, g4_markers)
        result["reasons"].append(
            "Ultra-processing marker(s) declared: " + ", ".join(g4_markers) + "."
        )
        result["evidence_strength"] = "direct_marker"
    elif group3 or (group1 and group2):
        # Group 3 (processed foods) takes precedence even when ambiguous terms
        # (antioxidant, raising agent, etc.) are present; these indicate added
        # processing without necessarily moving the product to group 4.
        result["group"] = 3
        result["group_name"] = GROUP_NAMES[3]
        result["status"] = "classified"
        result["supporting_ingredients"] = _supporting_items(data, group3 + [t for t in ambiguous if t in {"antioxidant", "raising agent"}])
        result["reasons"].append(
            "A recognisable food is combined with culinary substances or a preservation process."
        )
        result["evidence_strength"] = "ingredient_pattern"
    elif ambiguous:
        result["status"] = "uncertain"
        result["uncertainty"] = (
            "Only multifunction or processing aids were found (" + ", ".join(ambiguous)
            + "); their declared function is insufficient to separate NOVA group 3 from group 4."
        )
        result["supporting_ingredients"] = _supporting_items(data, ambiguous)
        result["reasons"].append("Ambiguous additive/processing terms require the declared technical function.")
        result["evidence_strength"] = "ambiguous"
    else:
        if group2 and not group1 and not group3:
            group = 2
            reason = "Ingredient list consists of culinary substances used for seasoning or cooking."
        elif group3 or (group1 and group2):
            group = 3
            reason = "A recognisable food is combined with culinary substances or a preservation process."
        elif group1 and not group2:
            group = 1
            reason = "Ingredient list contains recognisable foods with no added culinary substances."
        else:
            result["status"] = "uncertain"
            result["uncertainty"] = (
                "No authoritative NOVA marker was matched; classification from ingredient names alone is not reliable."
            )
            result["evidence_strength"] = "insufficient_markers"
            result["reasons"].append("Ingredient list did not contain enough recognised indicators.")
            group = None
            reason = ""

        if group is not None:
            result["group"] = group
            result["group_name"] = GROUP_NAMES[group]
            result["status"] = "classified"
            result["reasons"].append(reason)
            result["supporting_ingredients"] = _supporting_items(
                data, group1 + group2 + group3
            )
            result["evidence_strength"] = "ingredient_pattern"

    if external_valid:
        external["agrees_with_rules"] = result["group"] == external_group
        if result["status"] != "classified":
            result["group"] = external_group
            result["group_name"] = GROUP_NAMES[external_group]
            result["status"] = "external_source"
            result["reasons"].append(
                f"NOVA group {external_group} came from {external_source or 'an external source'}; "
                "the ingredient-only rules were inconclusive."
            )
            result["evidence_strength"] = "external_source"
            result["uncertainty"] = None
        elif not external["agrees_with_rules"]:
            result["reasons"].append(
                f"External NOVA group {external_group} disagrees with the ingredient-based group "
                f"{result['group']}; both are reported for review."
            )
            result["uncertainty"] = (
                "External and ingredient-based NOVA classifications conflict; review the ingredient list."
            )

    if result["status"] in {"uncertain", "external_source"}:
        result["missing_information"].append("declared technical function of ambiguous ingredients")
    return result
