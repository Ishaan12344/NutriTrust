"""
NutriTrust Configuration
All scoring constants, thresholds, and external API settings.
"""

import os

# ─────────────────────────────────────────────
# External API & OCR Settings
# ─────────────────────────────────────────────
OPEN_FOOD_FACTS_API = "https://world.openfoodfacts.org/api/v2/product"

# Sarvam AI OCR Settings
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "sk_1ru6jse3_dhCwTYo0WhKYWUCsNcYjiqpc")
SARVAM_API_URL = os.getenv("SARVAM_API_URL", "https://api.sarvam.ai")
OCR_CONFIDENCE_THRESHOLD = 0.3
OCR_LANGUAGES = ["en"]

# ─────────────────────────────────────────────
# WHO Daily Recommended Limits
# ─────────────────────────────────────────────
WHO_DAILY_LIMITS = {
    "energy_kcal": 2000,
    "total_fat": 65,        # grams
    "saturated_fat": 20,    # grams
    "trans_fat": 2,         # grams (WHO recommends <1% of energy)
    "sugar": 25,            # grams (free sugars)
    "sodium": 2000,         # milligrams
    "fiber": 25,            # grams (minimum target)
    "protein": 50,          # grams (minimum target)
}

# ─────────────────────────────────────────────
# NutriTrust Scoring Weights
# ─────────────────────────────────────────────
SCORING_WEIGHTS = {
    "nutrient_quality": 0.40,
    "nova_processing": 0.25,
    "nutrient_limits": 0.20,
    "additive_safety": 0.15,
}

# ─────────────────────────────────────────────
# Grade Thresholds
# ─────────────────────────────────────────────
GRADE_THRESHOLDS = [
    (85, "A+", "Excellent choice"),
    (70, "A",  "Good choice"),
    (55, "B",  "Moderate — check details"),
    (40, "C",  "Below average — consume cautiously"),
    (25, "D",  "Poor — high junk factor"),
    (0,  "F",  "Avoid — extremely unhealthy"),
]

# ─────────────────────────────────────────────
# Traffic Light Thresholds (per 100g) — UK FSA
# ─────────────────────────────────────────────
TRAFFIC_LIGHT_THRESHOLDS = {
    "sugar": {
        "green": 5.0,       # ≤5g per 100g
        "amber": 12.5,      # 5-12.5g per 100g
        # > 12.5 = red
    },
    "sodium": {
        "green": 120,       # ≤120mg per 100g
        "amber": 600,       # 120-600mg per 100g
        # > 600 = red
    },
    "saturated_fat": {
        "green": 1.5,       # ≤1.5g per 100g
        "amber": 5.0,       # 1.5-5g per 100g
        # > 5 = red
    },
    "energy_kcal": {
        "green": 100,       # ≤100kcal per 100g
        "amber": 250,       # 100-250kcal per 100g
        # > 250 = red
    },
}

# Traffic light scoring points
TRAFFIC_LIGHT_SCORES = {
    "green": 25,
    "amber": 15,
    "red": 5,
}

# ─────────────────────────────────────────────
# Nutri-Score Points Tables (per 100g)
# Negative points: higher = worse
# Positive points: higher = better
# ─────────────────────────────────────────────

# Energy (kJ) thresholds — we convert kcal to kJ (×4.184)
NUTRISCORE_NEGATIVE = {
    "energy_kj": [335, 670, 1005, 1340, 1675, 2010, 2345, 2680, 3015, 3350],
    "sugar":     [4.5, 9,  13.5, 18,   22.5, 27,   31,   36,   40,   45],
    "saturated_fat": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    "sodium":    [90, 180, 270, 360, 450, 540, 630, 720, 810, 900],
}

NUTRISCORE_POSITIVE = {
    "fiber":   [0.9, 1.9, 2.8, 3.7, 4.7],
    "protein": [1.6, 3.2, 4.8, 6.4, 8.0],
}
