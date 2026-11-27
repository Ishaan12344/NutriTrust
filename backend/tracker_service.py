"""Daily food tracker: scanned items, consumption status, totals and suggestions.

Items are stored with a client-supplied local date so daily/weekly/monthly
grouping is deterministic regardless of server timezone. MongoDB is used when
available, with the same local JSON fallback as the rest of the app.
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from database import get_db, get_profile

logger = logging.getLogger(__name__)

_TRACKER_FILE = Path(__file__).resolve().parent / "data" / "tracker_items.json"
_PERIODS = {"daily", "weekly", "monthly"}
_STATUSES = {"pending", "eaten", "not_eaten"}
_NUTRIENTS = (
    "energy_kcal",
    "protein",
    "total_carbohydrate",
    "total_fat",
    "saturated_fat",
    "sugar",
    "added_sugar",
    "fiber",
    "sodium",
    "calcium",
    "iron",
    "potassium",
)
_CORE_NUTRIENTS = ("energy_kcal", "protein", "total_carbohydrate", "total_fat")
_MAX_NAME = 120


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, 2) if number >= 0 else None


def _clean_list(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    cleaned = []
    for value in values:
        text = str(value).replace("en:", "").strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned[:50]


def _parse_date(value: Any) -> date:
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            pass
    return datetime.now(timezone.utc).date()


def _has_kidney_condition(profile: Mapping[str, Any] | None) -> bool:
    conditions = (profile or {}).get("conditions") or []
    if isinstance(conditions, str):
        conditions = [conditions]
    elif not isinstance(conditions, (list, tuple, set)):
        return False
    return any(
        "kidney" in str(condition).lower() or "renal" in str(condition).lower()
        for condition in conditions
    )


def _clean_username(username: Any) -> str:
    text = str(username or "").strip().lower()
    return text or "guest"


def _public_item(doc: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in doc.items() if key not in {"_id", "username"}}


def build_item_document(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a scan payload into the stored tracker item shape."""
    payload = payload if isinstance(payload, Mapping) else {}
    now = datetime.now(timezone.utc).isoformat()

    raw_nutrition = payload.get("nutrition") if isinstance(payload.get("nutrition"), Mapping) else {}
    nutrition = {key: _number(raw_nutrition.get(key)) for key in _NUTRIENTS}
    nutrition = {key: value for key, value in nutrition.items() if value is not None}
    missing = [key for key in _CORE_NUTRIENTS if nutrition.get(key) is None]

    name = str(payload.get("name") or "").strip()[: _MAX_NAME]
    needs_name = not name
    if needs_name:
        name = "Unnamed product"

    manual_name = bool(payload.get("manual_name")) or payload.get("source") == "manual_name"
    basis = str(payload.get("nutrition_basis") or "").strip()
    if basis not in {"per_serving", "per_100g"}:
        basis = "per_serving" if nutrition else "unknown"

    return {
        "item_id": uuid.uuid4().hex,
        "username": _clean_username(payload.get("username")),
        "name": name,
        "brand": str(payload.get("brand") or "").strip()[: _MAX_NAME] or None,
        "barcode": str(payload.get("barcode") or "").strip() or None,
        "image_url": payload.get("image_url") or None,
        "source": "manual_name" if manual_name else "scan",
        "manual_name": manual_name,
        "needs_name": needs_name,
        "status": "pending",
        "consumed_at": None,
        "local_date": _parse_date(payload.get("date")).isoformat(),
        "nutrition": nutrition,
        "nutrition_basis": basis,
        "allergens": _clean_list(payload.get("allergens")),
        "additives": _clean_list(payload.get("additives")),
        "nutri_grade": str(payload.get("nutri_grade") or "").strip() or None,
        "health_score": _number(payload.get("health_score")),
        "partial_data": bool(missing),
        "missing_fields": missing,
        "created_at": now,
        "updated_at": now,
    }


def _read_local() -> list[dict[str, Any]]:
    if not _TRACKER_FILE.exists():
        return []
    try:
        with open(_TRACKER_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, list) else []
    except Exception as exc:
        logger.warning("Could not read local tracker items: %s", exc)
        return []


def _write_local(items: list[dict[str, Any]]) -> None:
    try:
        _TRACKER_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_TRACKER_FILE, "w", encoding="utf-8") as handle:
            json.dump(items[-1000:], handle, indent=2)
    except Exception as exc:
        logger.error("Could not write local tracker items: %s", exc)


def add_tracker_item(payload: Mapping[str, Any]) -> dict[str, Any]:
    doc = build_item_document(payload)
    try:
        db = get_db()
        collection = db["tracker_items"]
        collection.create_index([("username", 1), ("local_date", 1)])
        collection.insert_one(dict(doc))
    except Exception as exc:
        logger.warning("MongoDB unavailable for tracker item (%s), saving locally", exc)
        items = _read_local()
        items.append(doc)
        _write_local(items)
    return _public_item(doc)


def update_tracker_item(item_id: str, username: Any, changes: Mapping[str, Any]) -> dict[str, Any]:
    """Update consumption status or a user-supplied name."""
    cleaned_user = _clean_username(username)
    updates: dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}

    status = changes.get("status")
    if status is not None:
        if status not in _STATUSES:
            raise ValueError("status must be pending, eaten or not_eaten.")
        updates["status"] = status
        updates["consumed_at"] = (
            datetime.now(timezone.utc).isoformat() if status == "eaten" else None
        )

    name = changes.get("name")
    if name is not None:
        cleaned_name = str(name).strip()[: _MAX_NAME]
        if not cleaned_name:
            raise ValueError("Enter a product name.")
        updates.update(
            {
                "name": cleaned_name,
                "manual_name": True,
                "source": "manual_name",
                "needs_name": False,
            }
        )

    if len(updates) == 1:
        raise ValueError("Provide a status or name to update.")

    try:
        db = get_db()
        collection = db["tracker_items"]
        collection.update_one({"item_id": item_id, "username": cleaned_user}, {"$set": updates})
        doc = collection.find_one({"item_id": item_id, "username": cleaned_user})
        if doc:
            return _public_item(doc)
    except Exception as exc:
        logger.warning("MongoDB unavailable for tracker update (%s), updating locally", exc)

    items = _read_local()
    for item in items:
        if item.get("item_id") == item_id and item.get("username") == cleaned_user:
            item.update(updates)
            _write_local(items)
            return _public_item(item)
    raise ValueError("Tracker item not found.")


def delete_tracker_item(item_id: str, username: Any) -> None:
    """Delete an item from MongoDB and any local fallback copy."""
    cleaned_user = _clean_username(username)
    query = {"item_id": item_id, "username": cleaned_user}
    deleted = False

    try:
        result = get_db()["tracker_items"].delete_one(query)
        deleted = result.deleted_count > 0
    except Exception as exc:
        logger.warning("MongoDB unavailable for tracker deletion (%s), deleting locally", exc)

    items = _read_local()
    remaining = [
        item
        for item in items
        if not (
            item.get("item_id") == item_id
            and item.get("username") == cleaned_user
        )
    ]
    deleted_local = len(remaining) < len(items)
    if deleted_local:
        _write_local(remaining)

    if not deleted and not deleted_local:
        raise ValueError("Tracker item not found.")


def list_tracker_items(username: Any, start: date, end: date) -> list[dict[str, Any]]:
    cleaned_user = _clean_username(username)
    try:
        db = get_db()
        docs = db["tracker_items"].find(
            {
                "username": cleaned_user,
                "local_date": {"$gte": start.isoformat(), "$lte": end.isoformat()},
            }
        ).sort("created_at", -1)
        items = [_public_item(doc) for doc in docs]
        if items:
            return items
    except Exception as exc:
        logger.warning("Could not read tracker items from MongoDB: %s", exc)

    return [
        _public_item(item)
        for item in reversed(_read_local())
        if item.get("username") == cleaned_user
        and start.isoformat() <= str(item.get("local_date")) <= end.isoformat()
    ]


def period_range(period: str, anchor: date) -> tuple[date, date]:
    if period not in _PERIODS:
        raise ValueError("period must be daily, weekly or monthly.")
    if period == "weekly":
        start = anchor - timedelta(days=anchor.weekday())
        return start, start + timedelta(days=6)
    if period == "monthly":
        start = anchor.replace(day=1)
        next_month = (start + timedelta(days=32)).replace(day=1)
        return start, next_month - timedelta(days=1)
    return anchor, anchor


def daily_targets(profile: Mapping[str, Any] | None) -> dict[str, float]:
    """Return general adult targets, or no targets for profiles under age 19."""
    profile = profile or {}
    gender = str(profile.get("gender") or "").lower()
    raw_weight = profile.get("weight")
    try:
        weight = float(raw_weight) if raw_weight is not None else None
        if weight is not None and (not math.isfinite(weight) or weight <= 0):
            weight = None
    except (TypeError, ValueError, OverflowError):
        weight = None
    raw_age = profile.get("age")
    try:
        age = int(raw_age) if raw_age is not None else None
    except (TypeError, ValueError, OverflowError):
        age = None

    if age is not None and age < 19:
        return {}

    energy = 2000.0
    protein = weight * 0.8 if weight is not None else 50.0
    if age is not None and weight is not None:
        if gender.startswith("m"):
            if age < 30:
                bmr = 15.057 * weight + 692.2
            elif age < 60:
                bmr = 11.472 * weight + 873.1
            else:
                bmr = 11.711 * weight + 587.7
        elif gender.startswith("f"):
            if age < 30:
                bmr = 14.818 * weight + 486.6
            elif age < 60:
                bmr = 8.126 * weight + 845.6
            else:
                bmr = 9.082 * weight + 658.5
        else:
            if age < 30:
                bmr = ((15.057 * weight + 692.2) + (14.818 * weight + 486.6)) / 2
            elif age < 60:
                bmr = ((11.472 * weight + 873.1) + (8.126 * weight + 845.6)) / 2
            else:
                bmr = ((11.711 * weight + 587.7) + (9.082 * weight + 658.5)) / 2
        energy = bmr * 1.4

    calcium = (
        1200.0
        if (gender.startswith("f") and age is not None and age >= 51)
        or (gender.startswith("m") and age is not None and age >= 71)
        or (not gender.startswith(("f", "m")) and age is not None and age >= 51)
        else 1000.0
    )
    iron = 8.0 if gender.startswith("m") or (age is not None and age > 50) else 18.0
    targets = {
        "energy_kcal": round(energy, 1),
        "protein": round(protein, 1),
        "total_carbohydrate": round(energy * 0.60 / 4, 1),
        "total_fat": round(energy * 0.30 / 9, 1),
        "saturated_fat": round(energy * 0.10 / 9, 1),
        "added_sugar": round(energy * 0.10 / 4, 1),
        "fiber": 25.0,
        "sodium": 2000.0,
        "calcium": calcium,
        "iron": iron,
        "potassium": 3510.0,
    }
    if _has_kidney_condition(profile):
        targets.pop("protein")
        targets.pop("potassium")
    return targets


def _target_note(profile: Mapping[str, Any] | None, targets_available: bool) -> str:
    kidney_note = (
        " A kidney-related condition is in the profile, so protein and potassium goals are "
        "hidden; follow clinician guidance."
        if _has_kidney_condition(profile)
        else ""
    )
    if not targets_available:
        return (
            "Adult targets are not shown for people under 19. Nutrition needs vary "
            "with growth; use age-specific guidance from a qualified professional."
            + kidney_note
        )

    profile = profile or {}
    raw_age = profile.get("age")
    raw_weight = profile.get("weight")
    try:
        age = int(raw_age) if raw_age is not None else None
        weight = float(raw_weight) if raw_weight is not None else None
    except (TypeError, ValueError, OverflowError):
        age = None
        weight = None

    if age is None or weight is None or not math.isfinite(weight) or weight <= 0:
        return (
            "General adult reference used because age or weight is missing. These "
            "estimates are not tailored for pregnancy, lactation or medical conditions."
            + kidney_note
        )
    gender = str(profile.get("gender") or "").lower()
    if not gender.startswith(("f", "m")):
        return (
            "Profile-based adult estimate: Schofield BMR × an assumed inactive PAL of 1.4. "
            "Because profile gender is not male/female, calories average the two equations "
            "(a fallback, not a validated non-binary-specific equation), and iron uses the "
            "higher reference through age 50. Carbohydrates use the midpoint of WHO's 45–75% "
            "energy range; added sugar is only a label-based proxy for free sugars. Not tailored "
            "for pregnancy, lactation or medical conditions."
            + kidney_note
        )
    return (
        "Profile-based adult estimate: Schofield BMR × an assumed inactive PAL of 1.4. "
        "Carbohydrates use the midpoint of WHO's 45–75% energy range; added sugar is "
        "only a label-based proxy for free sugars. Not tailored for pregnancy, "
        "lactation or medical conditions."
        + kidney_note
    )


def _empty_totals() -> dict[str, float]:
    return {key: 0.0 for key in _NUTRIENTS}


def _counts(items: list[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "eaten": sum(1 for item in items if item.get("status") == "eaten"),
        "not_eaten": sum(1 for item in items if item.get("status") == "not_eaten"),
        "pending": sum(1 for item in items if item.get("status") == "pending"),
    }


def _period_label(period: str, start: date, end: date) -> str:
    if period == "daily":
        return start.strftime("%a, %d %b")
    if period == "monthly":
        return start.strftime("%B %Y")
    if start.month == end.month:
        return f"{start.day}–{end.day} {start.strftime('%b %Y')}"
    if start.year == end.year:
        return f"{start.strftime('%d %b')} – {end.strftime('%d %b %Y')}"
    return f"{start.strftime('%d %b %Y')} – {end.strftime('%d %b %Y')}"


def _period_phrase(period: str) -> str:
    return {"daily": "today", "weekly": "this week", "monthly": "this month"}[period]


def _recommendations(
    totals: Mapping[str, float],
    targets: Mapping[str, float],
    period: str,
    profile: Mapping[str, Any] | None,
    eaten_items: list[Mapping[str, Any]],
    partial_count: int,
) -> list[dict[str, str]]:
    phrase = _period_phrase(period)
    if not eaten_items:
        return [
            {
                "type": "info",
                "title": "Nothing marked eaten yet",
                "message": f"Mark the items you actually ate {phrase} to see personalised suggestions.",
            }
        ]

    def ratio(key: str) -> float:
        target = float(targets.get(key) or 0)
        return float(totals.get(key) or 0) / target if target else 0.0

    recommendations: list[dict[str, str]] = []
    if ratio("sodium") >= 1:
        recommendations.append(
            {
                "type": "avoid",
                "title": "Go easy on salt",
                "message": f"You have reached {ratio('sodium') * 100:.0f}% of your sodium limit {phrase}. Skip salty snacks and check labels on sauces.",
            }
        )
    if ratio("added_sugar") >= 1:
        recommendations.append(
            {
                "type": "avoid",
                "title": "Added sugar is at its limit",
                "message": f"Recorded added sugar is at {ratio('added_sugar') * 100:.0f}% of the WHO free-sugar limit {phrase}. Labels may not report all free sugars.",
            }
        )
    if ratio("energy_kcal") >= 1.1:
        recommendations.append(
            {
                "type": "avoid",
                "title": "Calories above target",
                "message": f"You are {ratio('energy_kcal') * 100 - 100:.0f}% over your calorie goal {phrase}. Keep the next meal lighter and vegetable-led.",
            }
        )
    if ratio("fiber") < 0.7:
        recommendations.append(
            {
                "type": "eat",
                "title": "Add a fibre source",
                "message": f"You have {ratio('fiber') * 100:.0f}% of your fibre goal {phrase}. A fruit, dal or whole-grain serving would close the gap.",
            }
        )
    if "protein" in targets and ratio("protein") < 0.7:
        recommendations.append(
            {
                "type": "eat",
                "title": "Protein is running low",
                "message": f"You have {ratio('protein') * 100:.0f}% of your protein goal {phrase}. Add eggs, paneer, dal, tofu or lean meat to your next meal.",
            }
        )
    if "calcium" in targets and ratio("calcium") < 0.7:
        recommendations.append(
            {
                "type": "eat",
                "title": "Top up calcium",
                "message": f"You have {ratio('calcium') * 100:.0f}% of your calcium goal {phrase}. Milk, curd, tofu or a fortified drink can help.",
            }
        )
    if "iron" in targets and ratio("iron") < 0.7:
        recommendations.append(
            {
                "type": "eat",
                "title": "Iron is below target",
                "message": f"You have {ratio('iron') * 100:.0f}% of your iron goal {phrase}. Add leafy greens, legumes or fortified cereal.",
            }
        )

    allergies = {str(value).strip().lower() for value in (profile or {}).get("allergies") or []}
    if allergies:
        matched = sorted(
            {
                allergen
                for item in eaten_items
                for allergen in item.get("allergens") or []
                if str(allergen).strip().lower() in allergies
            }
        )
        if matched:
            recommendations.insert(
                0,
                {
                    "type": "avoid",
                    "title": "Allergy profile match",
                    "message": f"Items marked eaten list {', '.join(matched)}, which is in your allergy profile. Review before eating more.",
                },
            )

    if not recommendations:
        recommendations.append(
            {
                "type": "good",
                "title": "Nicely balanced",
                "message": f"Your tracked intake is close to your targets {phrase}. Keep the same mix at your next meal.",
            }
        )
    if partial_count:
        recommendations.append(
            {
                "type": "info",
                "title": "Some data is partial",
                "message": f"{partial_count} tracked item{'s' if partial_count != 1 else ''} lack complete nutrition data, so these suggestions are less precise.",
            }
        )
    return recommendations


def build_snapshot(
    items: list[Mapping[str, Any]],
    profile: Mapping[str, Any] | None,
    period: str,
    anchor: date,
) -> dict[str, Any]:
    start, end = period_range(period, anchor)
    in_range = [
        item
        for item in items
        if start.isoformat() <= str(item.get("local_date")) <= end.isoformat()
    ]
    in_range.sort(key=lambda item: (str(item.get("local_date")), str(item.get("created_at"))), reverse=True)
    eaten = [item for item in in_range if item.get("status") == "eaten"]

    targets = daily_targets(profile)
    targets_available = bool(targets)
    totals = _empty_totals()
    for item in eaten:
        for key in _NUTRIENTS:
            value = item.get("nutrition", {}).get(key) if isinstance(item.get("nutrition"), dict) else None
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[key] += float(value)
    totals = {key: round(value, 1) for key, value in totals.items()}

    days = []
    cursor = start
    while cursor <= end:
        day_items = [item for item in in_range if item.get("local_date") == cursor.isoformat()]
        day_eaten = [item for item in day_items if item.get("status") == "eaten"]
        day_totals = _empty_totals()
        for item in day_eaten:
            for key in _NUTRIENTS:
                value = item.get("nutrition", {}).get(key) if isinstance(item.get("nutrition"), dict) else None
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    day_totals[key] += float(value)
        days.append(
            {
                "date": cursor.isoformat(),
                "totals": {key: round(value, 1) for key, value in day_totals.items()},
                "counts": _counts(day_items),
            }
        )
        cursor += timedelta(days=1)

    trend_start = anchor - timedelta(days=6) if period == "daily" else start
    trend_days = []
    cursor = trend_start
    while cursor <= end:
        day_eaten = [
            item
            for item in items
            if item.get("local_date") == cursor.isoformat() and item.get("status") == "eaten"
        ]
        day_totals = _empty_totals()
        for item in day_eaten:
            for key in _NUTRIENTS:
                value = item.get("nutrition", {}).get(key) if isinstance(item.get("nutrition"), dict) else None
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    day_totals[key] += float(value)
        trend_days.append(
            {"date": cursor.isoformat(), "totals": {key: round(value, 1) for key, value in day_totals.items()}}
        )
        cursor += timedelta(days=1)

    day_count = max(1, (end - start).days + 1)
    period_targets = {key: round(value * day_count, 1) for key, value in targets.items()}
    percentages = {
        key: round(totals[key] / period_targets[key] * 100, 1)
        for key in targets
        if period_targets[key]
    }

    elapsed_end = min(end, datetime.now(timezone.utc).date())
    elapsed_days = max(1, (elapsed_end - start).days + 1)
    average = {key: round(totals[key] / elapsed_days, 1) for key in _NUTRIENTS}

    partial_count = sum(1 for item in eaten if item.get("partial_data"))
    counts = _counts(in_range)
    phrase = _period_phrase(period)
    protein_pct = percentages.get("protein", 0.0)
    if not eaten:
        highlight = f"No intake marked {phrase} yet."
    elif targets_available and "protein" in targets:
        highlight = f"You hit {protein_pct:.0f}% of your protein goal {phrase}."
    elif targets_available:
        highlight = "Some targets are hidden because of a health condition in your profile."
    else:
        highlight = "Adult nutrition targets are unavailable for this profile."

    nutrient_report_counts = {
        key: sum(
            1
            for item in eaten
            if isinstance(item.get("nutrition"), dict) and key in item["nutrition"]
        )
        for key in ("added_sugar",)
    }

    return {
        "success": True,
        "period": period,
        "anchor": anchor.isoformat(),
        "range": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "label": _period_label(period, start, end),
            "days": day_count,
        },
        "items": [_public_item(item) for item in in_range],
        "totals": totals,
        "targets": targets,
        "period_targets": period_targets,
        "percentages": percentages,
        "average": average,
        "days": days,
        "trend_days": trend_days,
        "counts": counts,
        "partial_data_count": partial_count,
        "highlight": highlight,
        "recommendations": (
            _recommendations(totals, period_targets, period, profile, eaten, partial_count)
            if targets_available
            else [
                {
                    "type": "info",
                    "title": "Adult targets unavailable",
                    "message": "Daily nutrient targets are not compared for people under 19.",
                }
            ]
        ),
        "has_data": bool(in_range),
        "targets_available": targets_available,
        "target_note": _target_note(profile, targets_available),
        "nutrient_report_counts": nutrient_report_counts,
    }


def get_tracker_snapshot(username: Any, period: str, anchor: date) -> dict[str, Any]:
    start, end = period_range(period, anchor)
    fetch_start = start - timedelta(days=6) if period == "daily" else start
    items = list_tracker_items(username, fetch_start, end)
    try:
        profile = get_profile(username=str(username or "")) if username else {}
    except (ValueError, RuntimeError) as exc:
        logger.info("tracker profile lookup skipped: %s", exc)
        profile = {}
    return build_snapshot(items, profile, period, anchor)
