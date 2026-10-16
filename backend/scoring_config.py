"""Configuration for the NutriTrust hybrid score.

This contains scoring constants only. Secrets and external-service settings stay
in the existing backend configuration and are not part of the scoring engine.
"""

WHO_DAILY_LIMITS = {
    "energy_kcal": 2000,
    "total_fat": 65,
    "saturated_fat": 20,
    "trans_fat": 2,
    "sugar": 25,
    "sodium": 2000,
    "fiber": 25,
    "protein": 50,
}

SCORING_WEIGHTS = {
    "nutrient_quality": 0.40,
    "nova_processing": 0.25,
    "nutrient_limits": 0.20,
    "additive_safety": 0.15,
}

GRADE_THRESHOLDS = [
    (85, "A+", "Excellent choice"),
    (70, "A", "Good choice"),
    (55, "B", "Moderate - check details"),
    (40, "C", "Below average - consume cautiously"),
    (25, "D", "Poor - high junk factor"),
    (0, "F", "Avoid - extremely unhealthy"),
]

# ``partial-v2`` keeps the component formulas intact but normalizes the weights
# of valid components when other components are unavailable.  Missing values are
# never represented as zero.
SCORING_FORMULA_VERSION = "hybrid-v1-partial-v2"

# UK front-of-pack thresholds for solid foods per 100 g. Energy is expressed in
# kJ, and salt—not sodium—is the official fourth traffic-light nutrient.
TRAFFIC_LIGHT_THRESHOLDS = {
    "total_fat": {"green": 3.0, "amber": 17.5, "unit": "g"},
    "sugar": {"green": 5.0, "amber": 22.5, "unit": "g"},
    "salt": {"green": 0.3, "amber": 1.5, "unit": "g"},
    "saturated_fat": {"green": 1.5, "amber": 5.0, "unit": "g"},
}

# UK solid-food colour bands use measured quantities per 100 g. Energy is
# printed as a value on the front-of-pack panel but is not traffic-light coloured.
CUSTOM_NUTRIENT_QUALITY_VERSION = "custom-fsa-threshold-transform-v1"
NOVA_TO_CUSTOM_SCORE = {1: 100, 2: 75, 3: 45, 4: 10}

TRAFFIC_LIGHT_SCORES = {"green": 25, "amber": 15, "red": 5}

CUSTOM_NUTRIENT_NEGATIVE = {
    "energy_kj": [335, 670, 1005, 1340, 1675, 2010, 2345, 2680, 3015, 3350],
    "sugar": [4.5, 9, 13.5, 18, 22.5, 27, 31, 36, 40, 45],
    "saturated_fat": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    "sodium": [90, 180, 270, 360, 450, 540, 630, 720, 810, 900],
}

CUSTOM_NUTRIENT_POSITIVE = {
    "fiber": [0.9, 1.9, 2.8, 3.7, 4.7],
    "protein": [1.6, 3.2, 4.8, 6.4, 8.0],
}
