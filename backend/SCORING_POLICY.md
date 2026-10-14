# NutriTrust scoring policy

Policy version: `hybrid-v1`. This is a product comparison aid, not a medical or
regulatory determination. Its component values are NutriTrust-specific and do
not replace the official classifications named below.

## Composite score

When all four component scores are available, the backend calculates:

`round(0.40 × nutrient_quality + 0.25 × nova_processing + 0.20 × nutrient_limits + 0.15 × additive_analysis)`

All components range from 0 to 100, with higher values intended to be better.
Unavailable components prevent the composite from being calculated; their
weights are not redistributed. The API returns the configured weights, each
component value, and its weighted contribution.

The component mappings preserve the supplied legacy engine: nutrient quality
uses its threshold point totals transformed to 0–100; NOVA groups map to
`1→100, 2→75, 3→45, 4→10`; traffic-light colors map to green 25, amber 15,
red 5, averaged over measured nutrients and scaled to 0–100; additive analysis
starts at 100 and deducts 5 for each distinct configured caution match and 15
for each distinct configured avoid match. This mapping is a product policy,
not an official scoring standard, and has not been clinically calibrated.

The overall grade thresholds are configured in `scoring_config.py`; they are
NutriTrust grades, not Nutri-Score grades. The score is labelled provisional
and reliability is explicitly marked not calibrated.

## Official classifications

- Nutri-Score is retained only as a sourced Open Food Facts reported grade.
  NutriTrust does not calculate an independent official grade because category
  eligibility and the full current algorithm inputs are not established here.
- NOVA is used as a source-reported Open Food Facts group. Ingredient markers
  may be shown as evidence, but marker counts do not independently assign a
  NOVA group.
- UK front-of-pack colors use 2016 guidance for solid foods per 100 g. Energy
  is shown as a measured kJ value without a traffic-light color. Sodium is
  converted to salt equivalent as sodium × 2.5 when an explicit salt value is
  absent. Beverage results remain unavailable until per-100-ml data and the
  applicable beverage criteria are supported.

## Additive reference limits

The local JSON reference is a limited hand-curated dataset, not an authoritative
regulatory database. A match without a configured concern is not a safety
guarantee. Unknown codes or an OFF additive count larger than the matched set
make the component unavailable. Regulatory approval, dosage limits, functions,
and jurisdiction-specific status are not independently verified by this app.
