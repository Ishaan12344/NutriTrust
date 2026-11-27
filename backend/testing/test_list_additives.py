import json

with open('D:/Projects/NutriTrust/backend/data/additive_regulatory.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

additives = data['additives']
print(f"Total additives: {len(additives)}")
print("\nAdditives with empty or missing category_rules:")
for key, val in additives.items():
    cat_rules = val.get('category_rules', [])
    if not cat_rules:
        print(f"  {key}: {val['name']} (permission={val.get('permission', 'unknown')})")

print("\nAdditives with populated category_rules:")
for key, val in additives.items():
    cat_rules = val.get('category_rules', [])
    if cat_rules:
        print(f"  {key}: {val['name']} ({len(cat_rules)} rules, permission={val.get('permission', 'unknown')})")