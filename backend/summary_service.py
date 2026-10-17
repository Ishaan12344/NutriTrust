"""Optional local-LLM summary of a NutriTrust analysis for one user.

The summary is produced by the Qwen2.5-1.5B-Instruct model bundled under
``models/``.  It explains a single scanned product to one person by combining
the user's saved health profile with the facts already computed by the pipeline
(merged product data, health findings, and the NutriTrust score).

Everything here is best-effort.  A disabled feature, a missing model, or a
generation error yields a payload whose ``status`` describes why instead of
raising, so the scan pipeline and its API contract are unaffected.

The prompt is built only from data the pipeline already produced.  The model is
instructed never to invent values, to say when data is missing, and never to
give medical advice or claim a product is safe.
"""

from __future__ import annotations

import logging
import re
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)

PROMPT_VERSION = "1.0"
MODEL_NAME = "Qwen2.5-1.5B-Instruct"
MAX_INGREDIENT_CHARS = 600
MAX_FINDINGS = 8

# Mirrors the labels used by the client's profile picker.  These are lookup
# hints for grounding the summary in explicit label text, not diagnoses.
ALLERGY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "peanuts": ("peanut", "groundnut"),
    "tree nuts": ("almond", "cashew", "walnut", "pistachio", "hazelnut", "tree nut"),
    "milk/dairy": ("milk", "dairy", "lactose", "casein", "whey", "butter", "cheese"),
    "eggs": ("egg", "albumin"),
    "soy": ("soy", "soya"),
    "wheat/gluten": ("wheat", "gluten", "barley", "rye"),
    "fish": ("fish",),
    "shellfish": ("shellfish", "crustacean", "shrimp", "prawn", "crab", "lobster"),
    "sesame": ("sesame", "til"),
}

SYSTEM_PROMPT = (
    "You are NutriTrust, a careful nutrition assistant. You write one short "
    "summary of a scanned food product for one person, using ONLY the facts in "
    "the user message. "
    "Rules you must always follow:\n"
    "- Write 3 or 4 short sentences in the second person ('you').\n"
    "- Use only the person's allergies, health conditions, and dietary "
    "preferences; never mention their name, age, weight, or gender.\n"
    "- Mention only the health conditions, allergies, and preferences that the "
    "facts show are relevant to this product.\n"
    "- Never state or hint that the product contains or does not contain a "
    "specific allergen unless the allergy check reports a match for it.\n"
    "- Only name a nutrient level such as 'high sugar' if that nutrient has a "
    "value in the facts; a fact marked 'not available' must be described as "
    "unknown, never guessed.\n"
    "- Describe nutrient levels exactly as the facts give them (for example "
    "'the high sugar band' or 'the medium sodium band'). Never call a medium "
    "value high or excessive, and never invent limits, daily intakes, or "
    "comparisons that are not in the facts.\n"
    "- If the allergy check reports a match, that is the most important point "
    "and must appear in the summary; if it reports no match, do not claim the "
    "product is allergen-free.\n"
    "- Say clearly when important information is missing.\n"
    "- Do not diagnose, do not give medical advice, and do not call the product "
    "safe, unsafe, healthy, or harmful.\n"
    "- Output only the summary text, with no heading, bullets, or sign-off."
)

# Reentrant so ``generate_text`` can hold the lock around a call that may load
# the model, while ``_load_bundle`` takes the same lock.
_model_lock = threading.RLock()
_bundle: tuple[Any, Any] | None = None


# ---------------------------------------------------------------------------
# Context building
# ---------------------------------------------------------------------------

def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _number(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _join_items(values: Any) -> list[str]:
    if isinstance(values, (list, tuple, set)):
        return [item for item in (_text(v) for v in values) if item]
    single = _text(values)
    return [single] if single else []


def profile_context(profile: Any) -> list[str]:
    """Describe the user's saved profile as prompt lines.

    Only the fields that can change guidance for a product are included:
    allergies, health conditions, and dietary preferences.  Name, age, weight,
    and gender are deliberately omitted so the summary stays about the product
    and the model cannot restate personal details.
    """
    if not isinstance(profile, dict):
        return []
    lines: list[str] = []
    if allergies := _join_items(profile.get("allergies")):
        if other := _text(profile.get("allergy_other")):
            allergies.append(other)
        lines.append("Allergies: " + ", ".join(allergies))
    if conditions := _join_items(profile.get("conditions")):
        if other := _text(profile.get("condition_other")):
            conditions.append(other)
        lines.append("Health conditions: " + ", ".join(conditions))
    if preferences := _join_items(profile.get("preferences")):
        lines.append("Dietary preferences: " + ", ".join(preferences))
    return lines


def _nutrition_line(nutrition: Any) -> str | None:
    if not isinstance(nutrition, dict):
        return None
    parts: list[str] = []
    for name, item in nutrition.items():
        if not isinstance(item, dict):
            continue
        value = _number(item.get("value"))
        if value is None:
            continue
        unit = _text(item.get("unit")) or ""
        label = str(name).replace("_", " ")
        if name == "energy_kcal":
            label = "energy"
        parts.append(f"{label} {value} {unit}".strip())
    return ", ".join(parts) if parts else None


def _allergen_line(allergens: Any) -> list[str]:
    if not isinstance(allergens, dict):
        return []
    lines: list[str] = []
    if declaration := _text(allergens.get("declaration") or allergens.get("open_food_facts_declaration")):
        lines.append(f"Allergen declaration: {declaration}")
    if declared := _join_items(allergens.get("declared")):
        lines.append("Allergens declared: " + ", ".join(declared))
    traces = allergens.get("precautionary_traces")
    if isinstance(traces, dict):
        if trace_text := _text(traces.get("text")):
            lines.append(f"May contain (precautionary): {trace_text}")
    if trace_tags := _join_items(allergens.get("open_food_facts_tags")):
        lines.append("Allergen database tags: " + ", ".join(trace_tags))
    return lines


def _finding_lines(findings: Any) -> list[str]:
    if not isinstance(findings, list):
        return []
    ordered = [
        finding for finding in findings
        if isinstance(finding, dict)
        and _text(finding.get("severity")) in {"attention", "review"}
    ]
    # Attention findings are the product's strongest signals; keep them first
    # and bound the prompt so a large findings list cannot crowd out key facts.
    ordered.sort(key=lambda item: 0 if item.get("severity") == "attention" else 1)
    lines: list[str] = []
    for finding in ordered[:MAX_FINDINGS]:
        identifier = _text(finding.get("id")) or "finding"
        severity = _text(finding.get("severity")) or ""
        category = _text(finding.get("category")) or ""
        tag = ", ".join(part for part in (severity, category) if part)
        explanation = _text(finding.get("explanation"))
        if explanation:
            lines.append(f"{identifier} [{tag}]: {explanation}")
    return lines


def _product_text_blob(analysis: Any) -> str:
    """Collect the product's ingredient and allergen text for matching."""
    if not isinstance(analysis, dict):
        return ""
    parts: list[str | None] = []
    allergens = analysis.get("allergens") if isinstance(analysis.get("allergens"), dict) else {}
    parts.append(_text(allergens.get("declaration")))
    parts.append(_text(allergens.get("open_food_facts_declaration")))
    parts.extend(_join_items(allergens.get("declared")))
    parts.extend(_join_items(allergens.get("open_food_facts_tags")))
    traces = allergens.get("precautionary_traces")
    if isinstance(traces, dict):
        parts.append(_text(traces.get("text")))
        parts.extend(_join_items(traces.get("allergens")))
    ingredients = analysis.get("ingredients") if isinstance(analysis.get("ingredients"), dict) else {}
    parts.append(_text(ingredients.get("text")))
    parts.extend(_join_items(ingredients.get("items")))
    return " ".join(part for part in parts if part)


def _profile_allergies(profile: Any) -> list[str]:
    """Return the profile's allergies, minus the non-specific picker options."""
    if not isinstance(profile, dict):
        return []
    allergies = _join_items(profile.get("allergies"))
    if other := _text(profile.get("allergy_other")):
        allergies.append(other)
    return [
        allergy for allergy in allergies
        if allergy.casefold() not in {"other", "no known food allergies"}
    ]


def _allergy_keywords(allergy: str) -> tuple[str, ...]:
    return ALLERGY_KEYWORDS.get(allergy.casefold(), (allergy.casefold(),))


def allergy_results(profile: Any, analysis: Any) -> list[tuple[str, str | None, bool]]:
    """Match the profile's allergies against the product text.

    Returns ``(allergy, matched_keyword_or_None, data_available)`` for each
    allergy.  ``data_available`` is False when there is no ingredient or allergen
    text at all, which means the allergy genuinely could not be checked.  A None
    keyword with data present means "not mentioned", which is not proof of
    absence.  The result only ever reflects explicit keyword matches.
    """
    allergies = _profile_allergies(profile)
    if not allergies:
        return []
    blob = _product_text_blob(analysis).casefold()
    if not blob:
        return [(allergy, None, False) for allergy in allergies]
    results: list[tuple[str, str | None, bool]] = []
    for allergy in allergies:
        match = next(
            (
                keyword for keyword in _allergy_keywords(allergy)
                if re.search(rf"\b{re.escape(keyword)}", blob)
            ),
            None,
        )
        results.append((allergy, match, True))
    return results


def allergy_check(profile: Any, analysis: Any) -> list[str]:
    """Format the allergy check as prompt lines."""
    results = allergy_results(profile, analysis)
    if not results:
        return []
    if not any(available for _, _, available in results):
        return [
            "Allergy check: ingredient and allergen data are unavailable, so this "
            "person's allergies could not be checked. Do not say whether the "
            "product contains any allergen."
        ]
    lines: list[str] = []
    for allergy, match, _ in results:
        if match:
            lines.append(
                f"Allergy check: '{match}' appears in the product's ingredient or "
                f"allergen data and matches the {allergy} allergy."
            )
        else:
            lines.append(
                f"Allergy check: no '{allergy}' keyword appears in the available "
                "ingredient or allergen data; this is not proof it is absent."
            )
    return lines


def _allergy_sentence(profile: Any, analysis: Any) -> str | None:
    """Format the allergy check as a plain sentence for a fallback summary."""
    results = allergy_results(profile, analysis)
    if not results:
        return None
    present = [allergy for allergy, match, _ in results if match]
    unverified = [allergy for allergy, match, _ in results if not match]
    sentences: list[str] = []
    if present:
        sentences.append(
            "The label or Open Food Facts mentions " + " and ".join(present)
            + ", which matches your allergy profile."
        )
    if unverified:
        sentences.append(
            "Because ingredient and allergen data are incomplete or missing, your "
            + ", ".join(unverified) + " allergy could not be checked against this product."
        )
    return " ".join(sentences) or None


def _has_allergen_data(analysis: Any) -> bool:
    if not isinstance(analysis, dict):
        return False
    allergens = analysis.get("allergens") if isinstance(analysis.get("allergens"), dict) else {}
    if _text(allergens.get("declaration")) or _text(allergens.get("open_food_facts_declaration")):
        return True
    if _join_items(allergens.get("declared")) or _join_items(allergens.get("open_food_facts_tags")):
        return True
    traces = allergens.get("precautionary_traces")
    if isinstance(traces, dict) and (_text(traces.get("text")) or _join_items(traces.get("allergens"))):
        return True
    return False


def _per_100g(analysis: Any) -> dict[str, Any]:
    if not isinstance(analysis, dict):
        return {}
    nutrition = analysis.get("nutrition") if isinstance(analysis.get("nutrition"), dict) else {}
    per_100g = nutrition.get("per_100g")
    return per_100g if isinstance(per_100g, dict) else {}


def has_nutrition(analysis: Any) -> bool:
    """True when at least one nutrient has a usable per-100 g value."""
    return any(
        isinstance(item, dict) and _number(item.get("value")) is not None
        for item in _per_100g(analysis).values()
    )


def data_sufficiency(analysis: Any) -> str:
    """Return ``\"none\"`` when the analysis has nothing the model can reason from.

    A product with no nutrients, no ingredient text, and no allergen text can
    only produce a made-up summary, so callers use the deterministic fallback
    instead of the model.
    """
    if not isinstance(analysis, dict) or not analysis:
        return "none"
    if has_nutrition(analysis) or _product_text_blob(analysis):
        return "some"
    return "none"


def fallback_summary(profile: Any, analysis: Any) -> str:
    """Build an accurate, deterministic summary without the model.

    Used when there is nothing to reason from, and as a safety net when the
    model's output cannot be trusted.  It only restates facts the pipeline
    already computed.
    """
    product = analysis.get("product") if isinstance(analysis.get("product"), dict) else {}
    name = _text(product.get("name"))
    brand = _text(product.get("brands") or product.get("brand"))
    label = name or brand or "This product"
    if name and brand:
        label = f"{name} ({brand})"

    sentences: list[str] = []
    scoring = analysis.get("scoring") if isinstance(analysis.get("scoring"), dict) else {}
    scores = scoring.get("scores") if isinstance(scoring.get("scores"), dict) else {}
    overall = _number(scores.get("overall"))
    if overall is not None:
        grade = _text(scores.get("grade"))
        sentences.append(
            f"{label} has a NutriTrust score of {overall}/100"
            + (f" (grade {grade})." if grade else ".")
        )
    else:
        sentences.append(
            f"{label} could not be scored because not enough of the data needed "
            "for the analysis was available."
        )

    health = analysis.get("health_analysis") if isinstance(analysis.get("health_analysis"), dict) else {}
    findings = health.get("findings") if isinstance(health.get("findings"), list) else []
    top = next(
        (
            finding for finding in findings
            if isinstance(finding, dict) and finding.get("severity") == "attention"
        ),
        None,
    )
    if top and (explanation := _text(top.get("explanation"))):
        sentences.append(explanation)

    if allergy_sentence := _allergy_sentence(profile, analysis):
        sentences.append(allergy_sentence)

    missing = [item.rstrip(". ") for item in _join_items(analysis.get("missing_data_warnings"))]
    if missing:
        sentences.append("Unavailable: " + "; ".join(missing) + ".")
        sentences.append(
            "Scanning the product's label instead of the barcode can supply what "
            "the barcode lookup is missing."
        )
    return " ".join(sentences)


# Claim patterns used to reject a model summary that asserts something the
# pipeline's facts do not support.  They are intentionally narrow so ordinary
# prose is not misread as a health claim.
_PRESENCE_CLAIM = r"(?:contains?|containing|presence of|includes?|made with)\b[^.]{0,30}\b{kw}"
_ABSENCE_CLAIM = (
    r"\b(?:free (?:from|of)|without|does not contain|doesn't contain|not contain|no)"
    r"\b[^.]{0,20}\b{kw}"
)
_NUTRIENT_WORDS: dict[str, str] = {
    "sugar": "sugar",
    "sugars": "sugar",
    "salt": "salt",
    "sodium": "sodium",
    "fat": "total_fat",
    "saturated fat": "saturated_fat",
    "fibre": "fiber",
    "fiber": "fiber",
    "protein": "protein",
    "carbohydrate": "total_carbohydrate",
    "carbohydrates": "total_carbohydrate",
    "calorie": "energy_kcal",
    "calories": "energy_kcal",
    "energy": "energy_kcal",
}
_BAND_WORDS = r"(?:high|higher|highest|low|lower|lowest|medium|moderate|excessive|elevated)"


def _claims_presence(text: str, allergy: str) -> bool:
    return any(
        re.search(_PRESENCE_CLAIM.replace("{kw}", re.escape(keyword)), text, re.IGNORECASE)
        for keyword in _allergy_keywords(allergy)
    )


def _claims_absence(text: str, allergy: str) -> bool:
    for keyword in _allergy_keywords(allergy):
        escaped = re.escape(keyword)
        if re.search(_ABSENCE_CLAIM.replace("{kw}", escaped), text, re.IGNORECASE):
            return True
        if re.search(rf"\b{escaped}[- ]free\b", text, re.IGNORECASE):
            return True
    return False


def _unsupported_band_claim(text: str, analysis: Any) -> str | None:
    """Return the nutrient word for a band claim with no value behind it."""
    available = {
        key for key, item in _per_100g(analysis).items()
        if isinstance(item, dict) and _number(item.get("value")) is not None
    }
    for word, key in _NUTRIENT_WORDS.items():
        pattern = rf"\b{_BAND_WORDS}\b[^.]{{0,25}}\b{re.escape(word)}\b"
        if key not in available and re.search(pattern, text, re.IGNORECASE):
            return word
    return None


def grounding_violation(summary: str, profile: Any, analysis: Any) -> str | None:
    """Describe how a summary contradicts the facts, or None when it is safe.

    This catches the two failure modes a small model shows on incomplete data:
    inventing an allergen conclusion, and describing a nutrient band for a
    nutrient the pipeline never measured.
    """
    for allergy, match, available in allergy_results(profile, analysis):
        if match is None and _claims_presence(summary, allergy):
            return (
                f"the summary claims {allergy} is present, but no matching allergen "
                "data was available"
            )
        if match is not None and _claims_absence(summary, allergy):
            return (
                f"the summary claims {allergy} is absent, but the product's data "
                "mentions it"
            )
    if re.search(r"\ballergen[- ]free\b", summary, re.IGNORECASE):
        return "the summary claims the product is allergen-free, which the data cannot establish"
    if word := _unsupported_band_claim(summary, analysis):
        return f"the summary describes a {word} band, but no {word} value was measured"
    return None


def product_context(analysis: Any) -> list[str]:
    """Describe the analysed product as prompt lines."""
    if not isinstance(analysis, dict):
        return []
    product = analysis.get("product") if isinstance(analysis.get("product"), dict) else {}
    lines: list[str] = []

    name = _text(product.get("name")) or _text((analysis.get("identification") or {}).get("name") if isinstance(analysis.get("identification"), dict) else None) or "Unknown product"
    brand = _text(product.get("brands") or product.get("brand"))
    lines.append(f"Product: {name}" + (f" (brand: {brand})" if brand else ""))
    if categories := _text(product.get("categories")):
        lines.append(f"Categories: {categories}")

    nutrition = analysis.get("nutrition") if isinstance(analysis.get("nutrition"), dict) else {}
    if per_100g := _nutrition_line(nutrition.get("per_100g")):
        lines.append(f"Nutrition per 100 g: {per_100g}")
    else:
        lines.append("Nutrition per 100 g: not available.")

    ingredients = analysis.get("ingredients") if isinstance(analysis.get("ingredients"), dict) else {}
    if ingredients_text := _text(ingredients.get("text")):
        lines.append("Ingredients: " + ingredients_text[:MAX_INGREDIENT_CHARS])
    else:
        lines.append("Ingredients: not available.")

    lines.extend(_allergen_line(analysis.get("allergens")))

    classification = analysis.get("classification") if isinstance(analysis.get("classification"), dict) else {}
    if nova := _number(classification.get("nova_group")):
        lines.append(f"NOVA group: {nova}")
    if grade := _text(classification.get("nutriscore_grade")):
        lines.append(f"Reported Nutri-Score grade: {grade}")
    if additives := _join_items(classification.get("additives_tags")):
        lines.append("Additives detected: " + ", ".join(additives))

    scoring = analysis.get("scoring") if isinstance(analysis.get("scoring"), dict) else {}
    scores = scoring.get("scores") if isinstance(scoring.get("scores"), dict) else {}
    overall = _number(scores.get("overall"))
    if overall is not None:
        grade = _text(scores.get("grade"))
        label = _text(scores.get("grade_label"))
        descriptor = " ".join(part for part in (grade, f"({label})" if label else None) if part)
        lines.append(f"NutriTrust score: {overall}/100" + (f" grade {descriptor}" if descriptor else ""))
        lines.append(
            "Note: the NutriTrust score is a NutriTrust composite, not an official "
            "Nutri-Score classification or medical judgment."
        )
    elif scoring:
        lines.append("NutriTrust score: not calculated (insufficient data).")
    if explanation := _text(scoring.get("explanation")):
        lines.append(f"Score breakdown: {explanation}")

    health = analysis.get("health_analysis") if isinstance(analysis.get("health_analysis"), dict) else {}
    lines.extend(_finding_lines(health.get("findings")))

    missing = _join_items(analysis.get("missing_data_warnings"))
    if missing:
        lines.append("Missing or unreadable data: " + "; ".join(missing))

    return lines


def build_messages(profile: Any, analysis: Any) -> list[dict[str, str]]:
    """Build the chat messages used to request the summary."""
    user_lines: list[str] = []
    profile_lines = profile_context(profile)
    product_lines = product_context(analysis)
    if profile_lines:
        user_lines.append("About this person:")
        user_lines.extend(f"- {line}" for line in profile_lines)
        user_lines.append("")
    else:
        user_lines.append("No health profile information is available for this person.")
        user_lines.append("")
    user_lines.append("About the scanned product:")
    user_lines.extend(f"- {line}" for line in product_lines)

    allergy_lines = allergy_check(profile, analysis)
    if allergy_lines:
        user_lines.append("")
        user_lines.append("Allergy check for this person:")
        user_lines.extend(f"- {line}" for line in allergy_lines)

    user_lines.append("")
    user_lines.append(
        "Write the summary now as 3 or 4 sentences: "
        "(1) name the product and its NutriTrust score; "
        "(2) if the allergy check reports a match, make that your first and most "
        "important point, otherwise state the single most important finding for "
        "this person's health conditions, using the exact nutrient band given; "
        "(3) add one more relevant fact only if the facts support it. "
        "Any fact marked 'not available' is unknown: say it is unknown rather than "
        "guessing, and never describe a nutrient level that is not listed. "
        "If the facts do not mention missing data, do not say anything is missing. "
        "Do not mention the person's name, age, weight, or gender."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(user_lines)},
    ]


# ---------------------------------------------------------------------------
# Orchestration (no model dependency; ``generate`` is injected)
# ---------------------------------------------------------------------------

def _describe(exc: BaseException) -> str:
    """A never-empty description, so a failure is always diagnosable."""
    text = str(exc).strip()
    if text:
        return text
    return exc.__class__.__name__


def _result(
    *,
    status: str,
    summary: str | None,
    source: str,
    details: dict[str, Any],
    reason: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "summary": summary,
        "source": source,
        **details,
    }
    if reason:
        payload["reason"] = reason
    return payload


def summarize_analysis(
    profile: Any,
    analysis: Any,
    *,
    generate: Callable[[list[dict[str, str]], int], str],
    max_new_tokens: int,
    model_name: str = MODEL_NAME,
    prompt_version: str = PROMPT_VERSION,
) -> dict[str, Any]:
    """Return a summary payload for the analysis, never raising on failure.

    The model writes the summary when the analysis has something to reason from
    and its output agrees with the pipeline's facts.  Otherwise a deterministic
    fallback is returned, so the caller always has text to show: incomplete
    barcode data never produces a blank result or an invented one.
    """
    details = {"model": model_name, "prompt_version": prompt_version}
    if not isinstance(analysis, dict) or not analysis:
        return _result(
            status="insufficient_data",
            summary=None,
            source="none",
            details={"model": None, "prompt_version": prompt_version},
            reason="No product analysis was provided to summarise.",
        )

    def fallback(status: str, reason: str | None) -> dict[str, Any]:
        return _result(
            status=status,
            summary=fallback_summary(profile, analysis),
            source="fallback",
            details={"model": None, "prompt_version": prompt_version},
            reason=reason,
        )

    # With nothing measured, neither the model nor a reader can draw any
    # conclusion, so answer factually without spending a generation on it.
    if data_sufficiency(analysis) == "none":
        return fallback("ok", "The analysis had no nutrition, ingredient, or allergen data to reason from.")

    messages = build_messages(profile, analysis)
    try:
        raw = generate(messages, max_new_tokens)
    except TimeoutError as exc:
        logger.warning("summary generation timed out: %s", _describe(exc))
        return fallback("ok", f"The model timed out: {_describe(exc)}")
    except Exception as exc:  # noqa: BLE001 - deliberate best-effort boundary
        logger.warning("summary generation failed: %s", _describe(exc))
        return fallback("ok", f"The model was unavailable: {_describe(exc)}")

    summary = " ".join(str(raw or "").split())
    if not summary:
        return fallback("ok", "The model returned an empty summary.")

    violation = grounding_violation(summary, profile, analysis)
    if violation:
        logger.warning("summary rejected by grounding check: %s", violation)
        return fallback("ok", f"The model summary was rejected because {violation}.")

    return _result(
        status="ok",
        summary=summary,
        source="model",
        details=details,
    )


# ---------------------------------------------------------------------------
# Local model loading and generation
# ---------------------------------------------------------------------------

def _load_bundle(model_path: str) -> tuple[Any, Any]:
    """Load and cache the tokenizer and model for ``model_path``.

    ``torch`` and ``transformers`` are imported lazily so importing this module
    (and therefore the FastAPI app) stays cheap and free of a hard dependency.
    """
    global _bundle
    with _model_lock:
        if _bundle is not None:
            return _bundle
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        logger.info("loading summary model from %s", model_path)
        tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.bfloat16 if device == "cuda" else torch.float32
        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            dtype=dtype,
            local_files_only=True,
            low_cpu_mem_usage=True,
        )
        model.to(device)
        model.eval()
        _bundle = (tokenizer, model)
        logger.info("summary model ready on %s (%s)", device, dtype)
        return _bundle


def _generate_locked(text_messages: list[dict[str, str]], max_new_tokens: int, model_path: str) -> str:
    import torch

    tokenizer, model = _load_bundle(model_path)
    prompt = tokenizer.apply_chat_template(
        text_messages, tokenize=False, add_generation_prompt=True
    )
    inputs = tokenizer([prompt], return_tensors="pt").to(model.device)
    with torch.inference_mode():
        output = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            repetition_penalty=1.05,
        )
    generated = output[:, inputs.input_ids.shape[1]:]
    return tokenizer.batch_decode(generated, skip_special_tokens=True)[0]


def _run_with_timeout(fn: Callable[[], Any], timeout_seconds: float) -> Any:
    """Run ``fn`` in a worker thread, raising TimeoutError past the deadline."""
    box: dict[str, Any] = {}

    def worker() -> None:
        try:
            box["value"] = fn()
        except Exception as exc:  # noqa: BLE001 - re-raised on the caller thread
            box["error"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout_seconds)
    if thread.is_alive():
        raise TimeoutError(f"summary generation exceeded {timeout_seconds:g}s")
    if "error" in box:
        raise box["error"]
    return box.get("value")


def generate_text(
    messages: list[dict[str, str]],
    max_new_tokens: int,
    *,
    model_path: str,
    timeout_seconds: float = 120.0,
) -> str:
    """Generate a summary with the local model, serialized and time-bounded."""
    # The lock serializes access to the single model instance; a timed-out
    # worker keeps it until it finishes so two requests never share the model.
    def run() -> str:
        with _model_lock:
            return _generate_locked(messages, max_new_tokens, model_path)

    return _run_with_timeout(run, timeout_seconds)
