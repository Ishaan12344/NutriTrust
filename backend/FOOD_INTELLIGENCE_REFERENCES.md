# Food intelligence reference register

This file records the authoritative sources used by the three assessment engines and the
implementation limits that must not be presented as verified science or regulation.

Verified on **2026-11-26**.

## 1. Nutri-Score — updated algorithm (2023)

Scope: the updated Nutri-Score algorithm approved in 2022/2023 and implemented from
2024 in several EU countries and from March 2025 in France.

Primary sources:

- Nutri-Score Q&A, updated algorithm, v11, 17 Mar 2025, approved by Santé publique France:
  https://www.santepubliquefrance.fr/sites/default/files/rdd/document/FAQ-updatedAlgo-V11.pdf
- French usage rules, Mar 2025: https://www.santepubliquefrance.fr/sites/default/files/rdd/document/mars2025RU-FR-vf.pdf
- Scientific Committee main report, voted 29 Jun 2022:
  https://www.aesan.gob.es/AECOSAN/docs/documentos/Nutri_Score/2022_main_algorithm_report_update_FINAL.pdf
- Scientific Committee beverages report V2-2023, voted 1 Feb 2023:
  https://www.aesan.gob.es/dam/jcr:c112a1e4-4a4d-4b13-96a7-5700aeff6057/report_beverages_2023.pdf.pdf
- Luxembourg regulation 30 Jan 2024, Annex 1-B "Algorithme Actualisé":
  https://legilux.public.lu/eli/etat/leg/rgd/2024/01/30/a80/jo
- Peer-reviewed summary: Nature Food 5, 102-110 (2024), DOI 10.1038/s43016-024-00920-3.

Implemented rules (`nutri_score_engine.py`):

- General solid-food negative and positive point tables, beverages table, red-meat protein cap,
  cheese protein inclusion, fats/oils/nuts/seeds saturated-fat energy table, and the beverage
  non-nutritive-sweetener +4 rule.
- Grade cut-offs: general/cheese/red meat `A<=0, B 1-2, C 3-10, D 11-18, E>=19`;
  fats/oils/nuts/seeds `A<=-6, B -5-2, C 3-10, D 11-18, E>=19`;
  beverages `A water only, B<=2, C 3-6, D 7-9, E>=10`.
- Energy conversion `kJ = kcal x 4.184`; salt from sodium `salt_g = sodium_mg x 2.5 / 1000`.

Implementation limits:

- Category detection from a free-text name is a heuristic and is reported in the result.
- Missing fibre, protein, or fruit/vegetable percentage is assigned zero points only when the
  result explicitly lists that assumption; missing mandatory inputs prevent a final grade.
- Fruit/vegetable/legume percentage must be supplied externally; NutriTrust does not fabricate
  a percentage from an ingredient list.
- Beverage values should be per 100 ml. Existing OCR data is per 100 g; this is reported, not silently converted.
- Non-nutritive sweetener detection from additive names uses a small common-name/code list and is
  labelled as a heuristic unless explicitly supplied.

## 2. NOVA — four-group framework

Sources:

- Monteiro et al., 2017, current four-group definitions:
  https://pmc.ncbi.nlm.nih.gov/articles/PMC10261019
- Monteiro et al., 2019, practical ingredient-label identification of ultra-processed foods:
  https://pmc.ncbi.nlm.nih.gov/articles/PMC10260459
- Monteiro et al., 2010 original three-group paper: https://pubmed.ncbi.nlm.nih.gov/21180977
- FAO, 2019, NOVA classification guide:
  https://openknowledge.fao.org/server/api/core/bitstreams/5277b379-0acb-4d97-a6a3-602774104629/content

Implemented rules (`nova_engine.py`, `data/nova_rules.json`):

- Group 1: recognisable foods with no added culinary substances.
- Group 2: single refined/extracted culinary substances.
- Group 3: recognisable food plus culinary substances or a traditional preservation process.
- Group 4: any declared non-culinary substance or cosmetic-additive class (the 2019 practical rule).
- Preservatives, antioxidants, stabilisers, raising agents, and similar multifunction aids are
  treated as ambiguous, not automatic group-4 proof.

Implementation limits:

- NOVA boundaries for cheese, canned foods, and multifunction additives are genuinely disputed.
- The engine returns evidence and uncertainty wording, never a validated probability.
- An unknown ingredient is not treated as ultra-processing merely because it is unfamiliar.
- An external NOVA group (for example from Open Food Facts) is reported and cross-checked, but
  it does not replace ingredient-level evidence.

## 3. FSSAI food additives

Sources:

- FSSAI Food Safety and Standards (Food Products Standards and Food Additives) Regulations, 2011:
  https://fssai.gov.in/upload/uploadfiles/files/Food_Additives_Regulations.pdf
- FSSAI Compendium, Appendix A v3 (01.08.2025):
  https://fssai.gov.in/docs/food-law/regulations/compendium/food-products-standards/Appendix%20A(4).pdf
- FSSAI Compendium, Chapter 3 v4 (01.08.2025):
  https://fssai.gov.in/docs/food-law/regulations/compendium/food-products-standards/Chapter%203_Substances%20added%20to%20food(1).pdf
- FSSAI amendments index:
  https://fssai.gov.in/food-law/regulations/amendments/food-products-standards
- FSSAI explicitly states that the compendium is a ready reference, not a legal document; original
  gazette notifications prevail.

Data structure (`data/additive_regulatory.json`):

- Reference register with document name, version/date, URL, and citation form.
- One record per additive: names/synonyms, INS/E aliases, functional class, permission basis,
  category-specific rules, maximum level with unit and basis, conditions, and reference section.
- The initial verified set covers E500, E621, E223, E503, E306, E320, E302, E330, E415 and E407.

Implementation limits:

- E306 could not be verified as an FSSAI INS number; Codex uses 307b for mixed tocopherols. The
  engine returns "unable to verify" rather than guessing.
- Without measured concentration data, compliance is always `compliance_not_verified`.
- A limit expressed as "residual SO2" or "on the fat or oil basis" is never compared with a
  result on a different basis.
- Permission is not a toxicological safety conclusion, and compliance does not mean the product
  is completely safe.
- The Annex-to-GMP list and the full gazette set are not reproduced; records carry that limitation
  in their notes and in every assessment.

## 4. Tracker nutrition estimates

Sources:

- FAO/WHO/UNU, *Human Energy Requirements* (2004), Chapter 5, adult Schofield BMR equations and
  the factorial relationship `TEE = BMR × PAL`:
  https://www.fao.org/4/y5686e/y5686e07.htm
- National Academies, *Dietary Reference Intakes for Energy* (2023), Chapters 5 and 7. Its
  current EER equations use age, sex, height, weight and physical-activity category:
  https://www.nationalacademies.org/read/26818/chapter/7
  https://www.nationalacademies.org/read/26818/chapter/9
- WHO, *Healthy diet* (26 Jan 2026), carbohydrate, fibre, free-sugar, total-fat, saturated-fat,
  sodium and potassium guidance:
  https://www.who.int/news-room/fact-sheets/detail/healthy-diet
- National Academies, *Dietary Reference Intakes for Calcium and Vitamin D* (2011):
  https://www.nationalacademies.org/read/13050/chapter/2
- National Academies, *Dietary Reference Intakes for Vitamin A, Vitamin K, ... Iron ...* (2001):
  https://www.nationalacademies.org/read/10026/chapter/2
- National Academies, *Dietary Reference Intakes for Energy, Carbohydrate, Fiber, Fat, Fatty
  Acids, Cholesterol, Protein, and Amino Acids* (2005):
  https://nap.nationalacademies.org/catalog/10490/dietary-reference-intakes-for-energy-carbohydrate-fiber-fat-fatty-acids-cholesterol-protein-and-amino-acids

Implemented guidance (`tracker_service.py`):

- For adults with age and weight, estimated energy is Schofield's age/sex/weight-based BMR
  multiplied by an assumed PAL of 1.4. If gender is not specified as male or female, the estimate
  uses the midpoint of those equations. If age or weight is unavailable, the tracker uses a
  2,000 kcal / 50 g protein general adult reference instead.
- Protein uses 0.8 g/kg/day when weight is available; otherwise the general reference is 50 g.
- The carbohydrate bar uses the midpoint of WHO's 45–75% energy range. Total-fat and saturated-fat
  bars use WHO upper limits of 30% and 10% of estimated energy, respectively.
- Added sugar is compared with WHO's free-sugar limit (<10% of energy) only as a label-based
  proxy. Total sugars remain separately displayed; labels may omit added sugar and do not capture
  all free sugars (for example, sugars in juice or honey).
- Fibre is 25 g/day for adults; sodium is below 2,000 mg/day; potassium is at least 3,510 mg/day.
  Calcium is 1,000 mg/day for most adults, rising to 1,200 mg/day for women aged 51+ and men aged
  71+; iron is 8 mg/day except for women aged 19–50, for whom it is 18 mg/day.
- Adult targets are not displayed for profiles younger than 19. All label-derived nutrient totals
  can be incomplete. These are general estimates, not clinical advice; they are not adjusted for
  pregnancy, lactation, kidney disease, hypertension, or other medical conditions.
- When a kidney-related condition is present in the profile, protein and potassium targets are
  withheld rather than suggesting universal values for a condition that can require clinical
  individualization.

Limitations:

- This is not the National Academies' current EER equation. Height and physical-activity level are
  not collected, so the 2023 equation cannot be used. The assumed PAL is not measured or inferred
  from the user's activity.
- FAO/WHO/UNU notes that the Schofield equations were largely based on historical European and
  North American datasets, so they may not predict every population equally well. The estimate
  should not be represented as an exact personal calorie requirement.
- Averaging the male/female Schofield estimates when profile gender is not in either category is a
  transparent fallback, not a validated non-binary-specific equation.
- Energy requirements are estimates rather than safe upper limits; body-weight trends and clinical
  context matter. Mineral reference values are population guidance, not treatment targets.
