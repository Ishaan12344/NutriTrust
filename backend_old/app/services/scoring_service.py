"""
Scoring Service
NutriTrust hybrid scoring engine combining:
  1. Nutri-Score (nutrient quality) — 40%
  2. NOVA classification (processing level) — 25%
  3. UK Traffic Light (nutrient limits) — 20%
  4. Additive safety analysis — 15%
"""

import json
import os
from app.config import (
    SCORING_WEIGHTS,
    GRADE_THRESHOLDS,
    TRAFFIC_LIGHT_THRESHOLDS,
    TRAFFIC_LIGHT_SCORES,
    NUTRISCORE_NEGATIVE,
    NUTRISCORE_POSITIVE,
    WHO_DAILY_LIMITS,
)

# ─────────────────────────────────────────────
# Load data files
# ─────────────────────────────────────────────
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

with open(os.path.join(_DATA_DIR, "additives.json"), "r", encoding="utf-8") as f:
    ADDITIVES_DB = json.load(f)

with open(os.path.join(_DATA_DIR, "nova_markers.json"), "r", encoding="utf-8") as f:
    NOVA_MARKERS = json.load(f)


def rate(product_data: dict) -> dict:
    """
    Compute the full NutriTrust rating for a product.

    Args:
        product_data: dict with keys 'product', 'nutrition_per_100g',
                      'ingredients_text', 'additives_tags', 'nova_group'

    Returns:
        Complete scoring result with overall score, grade, sub-scores, and explanations.
    """
    nutrition = product_data.get("nutrition_per_100g", {})
    ingredients_text = product_data.get("ingredients_text", "")
    additives_tags = product_data.get("additives_tags", [])
    known_nova = product_data.get("nova_group")

    # Check if nutrition data is completely missing (all zeros)
    is_data_missing = (
        nutrition.get("energy_kcal", 0) == 0 and
        nutrition.get("total_fat", 0) == 0 and
        nutrition.get("sugar", 0) == 0 and
        nutrition.get("sodium", 0) == 0 and
        not ingredients_text
    )

    # Compute all four sub-scores
    nutrient_result = _compute_nutrient_quality(nutrition)
    nova_result = _compute_nova_score(ingredients_text, known_nova)
    limits_result = _compute_nutrient_limits(nutrition)
    additive_result = _compute_additive_score(additives_tags, ingredients_text)

    if is_data_missing:
        overall_score = 0
        grade = "N/A"
        grade_label = "Incomplete Data"
        explanation = (
            "⚠️ Incomplete product data in the Open Food Facts database for this barcode. "
            "Nutrition values and ingredients are missing in the global record. "
            "Please switch to the 'Label Photo (OCR)' tab and upload a picture of your packet's label to extract exact values!"
        )
    else:
        # Weighted composite
        overall_score = round(
            (SCORING_WEIGHTS["nutrient_quality"] * nutrient_result["score"])
            + (SCORING_WEIGHTS["nova_processing"] * nova_result["score"])
            + (SCORING_WEIGHTS["nutrient_limits"] * limits_result["score"])
            + (SCORING_WEIGHTS["additive_safety"] * additive_result["score"])
        )
        overall_score = max(0, min(100, overall_score))
        grade, grade_label = _get_grade(overall_score)
        explanation = _generate_explanation(
            overall_score, grade, nutrition, nutrient_result, nova_result,
            limits_result, additive_result
        )


    return {
        "product": product_data.get("product", {}),
        "nutrition_per_100g": nutrition,
        "ingredients_text": ingredients_text,
        "additives_tags": additives_tags,
        "nova_group": known_nova if known_nova else nova_result["nova_group"],
        "scores": {
            "overall": overall_score,
            "grade": grade,
            "grade_label": grade_label,
            "nutrient_quality": {
                "score": nutrient_result["score"],
                "negative_points": nutrient_result["negative_points"],
                "positive_points": nutrient_result["positive_points"],
                "details": nutrient_result["details"],
            },
            "nova_processing": {
                "score": nova_result["score"],
                "nova_group": nova_result["nova_group"],
                "markers_found": nova_result["markers_found"],
                "details": nova_result["details"],
            },
            "nutrient_limits": {
                "score": limits_result["score"],
                "traffic_lights": limits_result["traffic_lights"],
                "details": limits_result["details"],
            },
            "additive_safety": {
                "score": additive_result["score"],
                "flagged_additives": additive_result["flagged_additives"],
                "total_additives": additive_result["total_additives"],
                "details": additive_result["details"],
            },
        },
        "explanation": explanation,
    }


# ─────────────────────────────────────────────
# 1. Nutrient Quality Score (Nutri-Score based)
#    Weight: 40%
# ─────────────────────────────────────────────

def _compute_nutrient_quality(nutrition: dict) -> dict:
    """
    Compute nutrient quality score based on Nutri-Score FSA-NPS algorithm.
    Negative points for bad nutrients, positive points for good nutrients.
    """
    energy_kcal = nutrition.get("energy_kcal") or 0
    sugar = nutrition.get("sugar") or 0
    sat_fat = nutrition.get("saturated_fat") or 0
    sodium = nutrition.get("sodium") or 0
    fiber = nutrition.get("fiber") or 0
    protein = nutrition.get("protein") or 0

    # Convert kcal to kJ for energy scoring
    energy_kj = energy_kcal * 4.184

    # Calculate negative points (0-10 each, max 40)
    neg_energy = _score_from_thresholds(energy_kj, NUTRISCORE_NEGATIVE["energy_kj"])
    neg_sugar = _score_from_thresholds(sugar, NUTRISCORE_NEGATIVE["sugar"])
    neg_sat_fat = _score_from_thresholds(sat_fat, NUTRISCORE_NEGATIVE["saturated_fat"])
    neg_sodium = _score_from_thresholds(sodium, NUTRISCORE_NEGATIVE["sodium"])

    negative_total = neg_energy + neg_sugar + neg_sat_fat + neg_sodium

    # Calculate positive points (0-5 each, max 10)
    pos_fiber = _score_from_thresholds(fiber, NUTRISCORE_POSITIVE["fiber"])
    pos_protein = _score_from_thresholds(protein, NUTRISCORE_POSITIVE["protein"])

    positive_total = pos_fiber + pos_protein

    # Raw score: lower is better (range: -10 to 40)
    raw_score = negative_total - positive_total

    # Map to 0-100 scale (inverted: -10 → 100, 40 → 0)
    score = round(max(0, min(100, 100 - (raw_score + 10) * 2)))

    # Generate details
    details_parts = []
    if neg_sugar >= 5:
        details_parts.append(f"High sugar ({sugar}g/100g)")
    if neg_sat_fat >= 5:
        details_parts.append(f"High saturated fat ({sat_fat}g/100g)")
    if neg_sodium >= 5:
        details_parts.append(f"High sodium ({sodium}mg/100g)")
    if neg_energy >= 5:
        details_parts.append(f"High energy density ({energy_kcal} kcal/100g)")
    if pos_fiber >= 3:
        details_parts.append(f"Good fiber content ({fiber}g/100g)")
    if pos_protein >= 3:
        details_parts.append(f"Good protein content ({protein}g/100g)")

    if not details_parts:
        details_parts.append("Moderate nutrient profile")

    return {
        "score": score,
        "negative_points": negative_total,
        "positive_points": positive_total,
        "raw_score": raw_score,
        "details": "; ".join(details_parts),
    }



def _score_from_thresholds(value: float, thresholds: list) -> int:
    """Score a value against ascending threshold list. Returns 0 to len(thresholds)."""
    for i, threshold in enumerate(thresholds):
        if value <= threshold:
            return i
    return len(thresholds)


# ─────────────────────────────────────────────
# 2. NOVA Processing Score
#    Weight: 25%
# ─────────────────────────────────────────────

def _compute_nova_score(ingredients_text: str, known_nova: int | None) -> dict:
    """
    Classify food by NOVA processing level.
    Uses known NOVA group from Open Food Facts if available,
    otherwise analyzes ingredient text for ultra-processing markers.
    """
    ingredients_lower = ingredients_text.lower() if ingredients_text else ""

    # Count NOVA 4 markers found in ingredients
    nova4_markers = NOVA_MARKERS.get("nova4_markers", [])
    found_markers = [
        marker for marker in nova4_markers if marker in ingredients_lower
    ]

    # Determine NOVA group
    if known_nova and isinstance(known_nova, int) and 1 <= known_nova <= 4:
        nova_group = known_nova
    else:
        marker_count = len(found_markers)
        if marker_count == 0:
            nova_group = 1
        elif marker_count <= 2:
            nova_group = 2
        elif marker_count <= 4:
            nova_group = 3
        else:
            nova_group = 4

    # Map NOVA group to score
    nova_to_score = {1: 100, 2: 75, 3: 45, 4: 10}
    score = nova_to_score.get(nova_group, 50)

    # Details
    nova_labels = {
        1: "Unprocessed or minimally processed",
        2: "Processed culinary ingredient",
        3: "Processed food",
        4: "Ultra-processed food product",
    }
    details = f"NOVA Group {nova_group}: {nova_labels.get(nova_group, 'Unknown')}"
    if found_markers:
        details += f". Markers found: {', '.join(found_markers[:5])}"
        if len(found_markers) > 5:
            details += f" (+{len(found_markers) - 5} more)"

    return {
        "score": score,
        "nova_group": nova_group,
        "markers_found": found_markers,
        "details": details,
    }


# ─────────────────────────────────────────────
# 3. Nutrient Limits Score (Traffic Light)
#    Weight: 20%
# ─────────────────────────────────────────────

def _compute_nutrient_limits(nutrition: dict) -> dict:
    """
    Compute per-nutrient traffic light ratings based on UK FSA thresholds.
    Each detected nutrient gets green (25), amber (15), or red (5).
    Missing (None) nutrients display as gray 'N/A' without giving fake green points.
    """
    traffic_lights = {}
    total_score = 0
    valid_count = 0

    nutrient_map = {
        "sugar": nutrition.get("sugar"),
        "sodium": nutrition.get("sodium"),
        "saturated_fat": nutrition.get("saturated_fat"),
        "energy_kcal": nutrition.get("energy_kcal"),
    }

    for nutrient, value in nutrient_map.items():
        if value is None:
            traffic_lights[nutrient] = {
                "color": "gray",
                "value": "N/A",
                "unit": "",
            }
            continue

        thresholds = TRAFFIC_LIGHT_THRESHOLDS.get(nutrient, {})
        green_limit = thresholds.get("green", 0)
        amber_limit = thresholds.get("amber", 0)

        if value <= green_limit:
            color = "green"
        elif value <= amber_limit:
            color = "amber"
        else:
            color = "red"

        traffic_lights[nutrient] = {
            "color": color,
            "value": value,
            "unit": "mg" if nutrient == "sodium" else ("kcal" if nutrient == "energy_kcal" else "g"),
        }
        total_score += TRAFFIC_LIGHT_SCORES[color]
        valid_count += 1

    # Scale score based on valid detected nutrients
    final_limits_score = round((total_score / (valid_count * 25)) * 100) if valid_count > 0 else 50

    # Build details
    reds = [n for n, tl in traffic_lights.items() if tl["color"] == "red"]
    ambers = [n for n, tl in traffic_lights.items() if tl["color"] == "amber"]
    greens = [n for n, tl in traffic_lights.items() if tl["color"] == "green"]
    grays = [n for n, tl in traffic_lights.items() if tl["color"] == "gray"]

    detail_parts = []
    if reds:
        detail_parts.append(f"🔴 High: {', '.join(_format_nutrient_name(n) for n in reds)}")
    if ambers:
        detail_parts.append(f"🟡 Moderate: {', '.join(_format_nutrient_name(n) for n in ambers)}")
    if greens:
        detail_parts.append(f"🟢 Low: {', '.join(_format_nutrient_name(n) for n in greens)}")
    if grays:
        detail_parts.append(f"⚪ Not detected: {', '.join(_format_nutrient_name(n) for n in grays)}")

    return {
        "score": final_limits_score,
        "traffic_lights": traffic_lights,
        "details": "; ".join(detail_parts) if detail_parts else "No data available",
    }



def _format_nutrient_name(name: str) -> str:
    """Format nutrient key to display name."""
    return name.replace("_", " ").replace("energy kcal", "calories").title()


# ─────────────────────────────────────────────
# 4. Additive Safety Score
#    Weight: 15%
# ─────────────────────────────────────────────

def _compute_additive_score(additives_tags: list, ingredients_text: str) -> dict:
    """
    Score food based on additive safety.
    Matches detected additives against curated database.
    Penalties: safe=0, caution=5, avoid=15
    """
    flagged = []
    penalty = 0
    matched_additives = []

    # Check tagged additives (from barcode lookup or OCR)
    for tag in additives_tags:
        tag_clean = tag.strip().upper()
        if tag_clean in ADDITIVES_DB:
            entry = ADDITIVES_DB[tag_clean]
            matched_additives.append(tag_clean)

            if entry["risk"] == "caution":
                penalty += 5
                flagged.append(f"{tag_clean} - {entry['name']} (⚠️ Caution: {entry['reason']})")
            elif entry["risk"] == "avoid":
                penalty += 15
                flagged.append(f"{tag_clean} - {entry['name']} (🚫 Avoid: {entry['reason']})")

    # Also scan ingredients text for additive names not caught by E-numbers
    if ingredients_text:
        ingredients_lower = ingredients_text.lower()
        for code, entry in ADDITIVES_DB.items():
            if code not in matched_additives:
                name_lower = entry["name"].lower()
                # Check if the additive's common name appears in ingredients
                if name_lower in ingredients_lower:
                    matched_additives.append(code)
                    if entry["risk"] == "caution":
                        penalty += 5
                        flagged.append(
                            f"{code} - {entry['name']} (⚠️ Caution: {entry['reason']})"
                        )
                    elif entry["risk"] == "avoid":
                        penalty += 15
                        flagged.append(
                            f"{code} - {entry['name']} (🚫 Avoid: {entry['reason']})"
                        )

    score = max(0, 100 - penalty)

    # Details
    if not matched_additives:
        details = "No flagged additives detected"
    else:
        safe_count = len(matched_additives) - len(flagged)
        details = f"{len(matched_additives)} additive(s) detected: {len(flagged)} flagged, {safe_count} safe"

    return {
        "score": score,
        "flagged_additives": flagged,
        "total_additives": len(matched_additives),
        "details": details,
    }


# ─────────────────────────────────────────────
# Grade Calculation
# ─────────────────────────────────────────────

def _get_grade(score: int) -> tuple:
    """Map overall score to letter grade and label."""
    for threshold, grade, label in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade, label
    return "F", "Avoid — extremely unhealthy"


# ─────────────────────────────────────────────
# Explanation Generator
# ─────────────────────────────────────────────

def _generate_explanation(
    overall_score: int,
    grade: str,
    nutrition: dict,
    nutrient_result: dict,
    nova_result: dict,
    limits_result: dict,
    additive_result: dict,
) -> str:
    """Generate a human-readable summary explanation."""
    parts = [f"This product scores {overall_score}/100 (Grade {grade})."]

    # Main concerns
    concerns = []
    positives = []

    # Sodium concern
    sodium = nutrition.get("sodium") or 0
    if sodium > 0:
        daily_pct = round((sodium / WHO_DAILY_LIMITS["sodium"]) * 100)
        if daily_pct > 30:
            concerns.append(f"very high sodium at {daily_pct}% of daily limit per 100g")
        elif daily_pct > 15:
            concerns.append(f"moderate sodium at {daily_pct}% of daily limit per 100g")

    # Sugar concern
    sugar = nutrition.get("sugar") or 0
    if sugar > 0:
        daily_pct = round((sugar / WHO_DAILY_LIMITS["sugar"]) * 100)
        if daily_pct > 30:
            concerns.append(f"high sugar at {daily_pct}% of daily limit per 100g")

    # Processing concern
    if nova_result["nova_group"] == 4:
        markers = nova_result["markers_found"][:3]
        if markers:
            concerns.append(
                f"ultra-processed (NOVA 4) with markers: {', '.join(markers)}"
            )
        else:
            concerns.append("classified as ultra-processed (NOVA 4)")
    elif nova_result["nova_group"] == 1:
        positives.append("minimally processed (NOVA 1)")

    # Additive concern
    if additive_result["flagged_additives"]:
        count = len(additive_result["flagged_additives"])
        concerns.append(f"{count} additive(s) flagged for caution/avoidance")

    # Good nutrients
    fiber = nutrition.get("fiber") or 0
    protein = nutrition.get("protein") or 0
    if fiber >= 3:
        positives.append(f"good fiber ({fiber}g/100g)")
    if protein >= 8:
        positives.append(f"good protein ({protein}g/100g)")


    if concerns:
        parts.append("Concerns: " + "; ".join(concerns) + ".")
    if positives:
        parts.append("Positives: " + "; ".join(positives) + ".")

    return " ".join(parts)
