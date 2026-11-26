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
