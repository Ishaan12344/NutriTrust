"""FSSAI-oriented additive identification and regulatory assessment.

Permission status and measured compliance are kept separate. A permission from
the official tables is never presented as proof that the product complies with
a maximum level; without concentration data the compliance result is
``compliance_not_verified``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).with_name("data") / "additive_regulatory.json"


def _merge_duplicate_objects(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Preserve a complete record when a later JSON entry adds category rules.

    The local source has some additive codes twice: the first entry has the
    identity and functional class, while the later entry supplies category
    notes.  The default JSON loader silently keeps only the last entry, which
    made recognised additives lose their names and broke assessment.
    """
    result: dict[str, Any] = {}
    for key, value in pairs:
        existing = result.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            result[key] = {**existing, **value}
        else:
            result[key] = value
    return result


# Some category-rule supplements repeat an additive code. Merge those records
# at load time so every additive retains its identity, function and rules.
_DATA = json.loads(
    DATA_PATH.read_text(encoding="utf-8"), object_pairs_hook=_merge_duplicate_objects
)
REFERENCES = _DATA["references"]
ADDITIVES = _DATA["additives"]
# Supplemental names and descriptions come from the legacy reference list;
# they do not establish regulatory permission.
_LEGACY_ADDITIVES = {
    code: {
        "name": str(entry.get("name") or ""),
        "purpose": str(entry.get("reason") or ""),
        "reference_risk": str(entry.get("risk") or ""),
    }
    for code, entry in json.loads(
        (Path(__file__).with_name("data") / "additives.json").read_text(
            encoding="utf-8"
        )
    ).items()
    if isinstance(entry, dict)
}

PERMISSION_LABELS = {
    "permitted_gmp": "permitted_gmp",
    "conditional_only": "permitted_with_conditions",
    "restricted": "restricted_or_not_permitted",
    "not_permitted": "restricted_or_not_permitted",
    "unable_to_verify": "unable_to_verify",
}


def _normalize_tag(tag: Any) -> str | None:
    if not isinstance(tag, str) or not tag.strip():
        return None
    value = re.sub(r"^en:", "", tag.strip(), flags=re.IGNORECASE)
    value = value.replace("-", "").replace(" ", "").upper()
    if re.fullmatch(r"E\d{3,4}[A-Z]?", value):
        return value
    if re.fullmatch(r"\d{3,4}[A-Z]?", value):
        return "E" + value
    return None


def _reference(ref_id: str, section: str | None = None) -> dict[str, Any]:
    source = REFERENCES.get(ref_id, {})
    result = {
        "document": source.get("document"),
        "version": source.get("version"),
        "citation": source.get("citation"),
        "url": source.get("url"),
        "section": section,
    }
    return result


def _category_rules(
    record: dict[str, Any], category: str | None
) -> list[dict[str, Any]]:
    if not category:
        return []
    lowered = category.casefold()
    return [
        rule
        for rule in record.get("category_rules", [])
        if isinstance(rule, dict)
        and isinstance(rule.get("category_patterns"), list)
        and any(pattern.casefold() in lowered for pattern in rule["category_patterns"])
    ]


def _detect(data: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[str], bool]:
    """Return canonical matches, unknown codes, and whether additive data was available."""
    tags = data.get("additives_tags")
    text = (
        data.get("ingredients_text")
        if isinstance(data.get("ingredients_text"), str)
        else ""
    )
    lowered = " ".join(text.casefold().split())
    available = bool(tags) or bool(
        re.search(r"\bE\s*\d{3,4}[A-Z]?\b", text, re.IGNORECASE)
    )
    if data.get("additives_available") is not None:
        available = bool(data["additives_available"]) or available

    detected: dict[str, dict[str, Any]] = {}
    unknown: list[str] = []
    for tag in tags or []:
        code = _normalize_tag(tag)
        if code is None:
            continue
        if code in ADDITIVES:
            detected.setdefault(code, {"detected_via": []})["detected_via"].append(
                "tag"
            )
        else:
            unknown.append(code)

    for match in re.finditer(r"\bE\s*(\d{3,4}[A-Z]?)\b", text, re.IGNORECASE):
        code = "E" + re.sub(r"\s+", "", match.group(1)).upper()
        if code in ADDITIVES:
            detected.setdefault(code, {"detected_via": []})["detected_via"].append(
                "ingredient_code"
            )
        else:
            unknown.append(code)

    for code, record in ADDITIVES.items():
        names = [
            name
            for name in (record.get("name"), *record.get("synonyms", []))
            if isinstance(name, str) and name.strip()
        ]
        if any(
            re.search(r"(?<!\w)" + re.escape(name.casefold()) + r"(?!\w)", lowered)
            for name in names
        ):
            detected.setdefault(code, {"detected_via": []})["detected_via"].append(
                "ingredient_name"
            )

    for item in detected.values():
        item["detected_via"] = list(dict.fromkeys(item["detected_via"]))
    return detected, sorted(set(unknown)), available


def _assess_one(
    code: str,
    detected_via: list[str],
    record: dict[str, Any] | None,
    category: str | None,
    concentrations: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    references: list[dict[str, Any]] = []
    if record is None:
        legacy = _LEGACY_ADDITIVES.get(code, {})
        name = legacy.get("name") or None
        purpose = legacy.get("purpose") or None
        return (
            {
                "identified_as": code,
                "name": name,
                "purpose": purpose,
                "reference_risk": legacy.get("reference_risk") or None,
                "notes": [],
                "regulatory_notes": [],
                "ins": [],
                "functional_class": [],
                "detected_via": detected_via,
                "permission_status": "unable_to_verify",
                "compliance_status": "compliance_not_verified",
                "applicable_rule": None,
                "max_level": None,
                "conditions": [],
                "reference": None,
                "limitations": [
                    (
                        f"Name shown from the project's reference additive list ({name}); "
                        if name
                        else ""
                    )
                    + "No verified FSSAI record is available for this additive code."
                ],
            },
            references,
            [
                f"{code} was identified but has no verified FSSAI record in the local reference data."
            ],
        )

    for ref_id in record.get("references", []):
        references.append(_reference(ref_id))
    legacy = _LEGACY_ADDITIVES.get(code, {})
    legacy_purpose = legacy.get("purpose") or None
    functional_class = record.get("functional_class", [])
    regulatory_notes = [
        {
            key: rule[key]
            for key in (
                "category",
                "fcs",
                "max_level",
                "conditions",
                "note",
                "reference",
            )
            if rule.get(key) is not None
        }
        for rule in record.get("category_rules", [])
        if isinstance(rule, dict)
        and any(
            rule.get(key) is not None
            for key in (
                "category",
                "fcs",
                "max_level",
                "conditions",
                "note",
                "reference",
            )
        )
    ]
    rules = _category_rules(record, category)
    permission = record.get("permission")
    applicable = None
    permission_status = PERMISSION_LABELS.get(permission, "unable_to_verify")
    if permission_status == "restricted_or_not_permitted":
        warnings.append(
            f"{code} is recorded as restricted or not permitted in the supplied FSSAI record."
        )
    elif permission_status == "unable_to_verify" and permission != "conditional_only":
        warnings.append(f"{code} could not be verified against FSSAI Appendix A.")
    elif rules:
        applicable = rules[0]
        permission_status = "permitted_with_conditions"
        references.append(
            _reference(
                applicable["reference"]["id"], applicable["reference"].get("section")
            )
        )
    elif permission == "permitted_gmp":
        permission_status = "permitted_gmp"
    elif permission == "conditional_only":
        permission_status = "unable_to_verify"
        warnings.append(
            f"{code} has only category-specific FSSAI permissions; a verified food category is required."
        )

    limitations = list(record.get("notes", []))
    if not category:
        limitations.append(
            "Food category was not supplied, so Annex-to-GMP exclusions could not be checked."
        )
    if applicable and applicable.get("max_level"):
        limitations.append(
            "Comparison requires a measured value on the same basis ("
            + applicable["max_level"]["basis"]
            + ")."
        )

    concentration = None
    for key in (code, code.replace("E", ""), record.get("name", "")):
        if key and key in concentrations:
            concentration = concentrations[key]
            break
    compliance = "compliance_not_verified"
    if concentration is not None:
        value = (
            concentration.get("mg_per_kg") if isinstance(concentration, dict) else None
        )
        basis = concentration.get("basis") if isinstance(concentration, dict) else None
        max_level = applicable.get("max_level") if applicable else None
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and max_level
        ):
            if basis == max_level.get("basis"):
                compliance = (
                    "compliant" if value <= max_level["value"] else "non_compliant"
                )
                limitations.append(
                    f"Measured {value} mg/kg was compared with the {max_level['value']} mg/kg "
                    f"limit on a {basis} basis."
                )
            else:
                warnings.append(
                    f"Concentration basis {basis!r} does not match limit basis "
                    f"{max_level.get('basis')!r}; compliance was not verified."
                )
        else:
            warnings.append(
                f"Concentration data for {code} lacked a comparable value and limit basis."
            )

    result = {
        "identified_as": code,
        "name": record.get("name"),
        "purpose": legacy_purpose,
        "reference_risk": legacy.get("reference_risk") or None,
        "notes": record.get("notes", []),
        "regulatory_notes": regulatory_notes,
        "ins": record.get("ins", []),
        "functional_class": functional_class,
        "detected_via": detected_via,
        "permission_status": permission_status,
        "compliance_status": compliance,
        "applicable_rule": applicable["category"] if applicable else None,
        "max_level": applicable.get("max_level") if applicable else None,
        "conditions": applicable.get("conditions", []) if applicable else [],
        "reference": (
            _reference(
                applicable["reference"]["id"], applicable["reference"].get("section")
            )
            if applicable
            else None
        ),
        "limitations": limitations,
    }
    return result, references, warnings


def assess_additives(data: dict[str, Any]) -> dict[str, Any]:
    """Assess identified additives against the verified FSSAI reference subset."""
    data = data if isinstance(data, dict) else {}
    category = data.get("category") if isinstance(data.get("category"), str) else None
    concentrations = (
        data.get("additive_concentrations")
        if isinstance(data.get("additive_concentrations"), dict)
        else {}
    )
    detected, unknown, available = _detect(data)

    results: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    warnings: list[str] = []
    for code, info in sorted(detected.items()):
        record = ADDITIVES.get(code)
        if isinstance(record, dict):
            record = {
                **record,
                "name": record.get("name")
                or _LEGACY_ADDITIVES.get(code, {}).get("name")
                or None,
            }
        if not isinstance(record, dict) or not record.get("name"):
            record = None
        item, item_refs, item_warnings = _assess_one(
            code, info["detected_via"], record, category, concentrations
        )
        results.append(item)
        references.extend(item_refs)
        warnings.extend(item_warnings)
    for code in unknown:
        item, item_refs, item_warnings = _assess_one(
            code, ["tag_or_code"], None, category, concentrations
        )
        results.append(item)
        references.extend(item_refs)
        warnings.extend(item_warnings)

    if not available and not results:
        overall = "insufficient_information"
        warnings.append(
            "Additive information was not available; the absence of detected additives was not inferred."
        )
    elif not results:
        overall = "no_additives_identified"
        warnings.append(
            "No additives were identified in the available additive information."
        )
    elif any(
        item["permission_status"] == "restricted_or_not_permitted" for item in results
    ):
        overall = "restricted_or_not_permitted"
    elif any(item["permission_status"] == "unable_to_verify" for item in results):
        overall = "insufficient_information"
    elif any(
        item["permission_status"] == "permitted_with_conditions" for item in results
    ):
        overall = "permitted_with_conditions"
    else:
        overall = "permitted_gmp"

    compliance_status = "compliance_not_verified"
    if results:
        statuses = {item["compliance_status"] for item in results}
        if "non_compliant" in statuses:
            compliance_status = "non_compliant"
        elif statuses == {"compliant"}:
            compliance_status = "compliant"

    unique_references = {
        (ref.get("document"), ref.get("section"), ref.get("version")): ref
        for ref in references
    }
    return {
        "overall_status": overall,
        "compliance_status": compliance_status,
        "additives": results,
        "warnings": list(dict.fromkeys(warnings)),
        "regulatory_references": list(unique_references.values()),
        "assessment_basis": _DATA["framework"],
        "important_notice": _DATA["important_notice"],
        "concentration_data_available": bool(concentrations),
        "limitations": [
            "Regulatory permission is not a toxicological safety conclusion.",
            "This assessment does not establish that the product is completely safe.",
            "FSSAI category-specific entries are limited to the verified records in additive_regulatory.json.",
        ],
    }
