import 'package:flutter/material.dart';

import '../models/health_profile.dart';

class PersonalizedInsights extends StatelessWidget {
  const PersonalizedInsights({super.key, required this.profile, required this.analysis});

  final HealthProfile profile;
  final Map<String, dynamic> analysis;

  Map<String, dynamic> _map(Object? value) =>
      value is Map ? Map<String, dynamic>.from(value) : <String, dynamic>{};
  List<Object?> _list(Object? value) => value is List ? value : <Object?>[];

  String? _nutrient(String key) {
    final nutrition = _map(analysis['nutrition']);
    final per100 = _map(nutrition['per_100g']);
    final item = _map(per100[key]);
    final value = item['value'];
    final unit = item['unit'];
    if (value is! num || unit == null) return null;
    return '${value % 1 == 0 ? value.toInt() : value} $unit per 100 g';
  }

  String _sourceText() {
    final ingredients = _map(analysis['ingredients'])['text'];
    final allergens = _map(analysis['allergens']);
    final traces = _map(allergens['precautionary_traces']);
    return [
      ingredients,
      allergens['declaration'],
      allergens['open_food_facts_declaration'],
      traces['text'],
      ..._list(allergens['declared']),
      ..._list(allergens['open_food_facts_tags']),
      ..._list(allergens['traces_tags']),
    ].where((item) => item != null).map((item) => (item ?? '').toString().toLowerCase()).join(' ');
  }

  String _allergyStatus(String allergy, String source) {
    const terms = <String, List<String>>{
      'Peanuts': ['peanut', 'groundnut'],
      'Tree nuts': ['almond', 'cashew', 'walnut', 'pistachio', 'hazelnut', 'tree nut'],
      'Milk/dairy': ['milk', 'dairy', 'lactose', 'casein', 'whey', 'butter', 'cheese'],
      'Eggs': ['egg', 'albumin'],
      'Soy': ['soy', 'soya'],
      'Wheat/gluten': ['wheat', 'gluten', 'barley', 'rye'],
      'Fish': ['fish'],
      'Shellfish': ['shellfish', 'crustacean', 'shrimp', 'prawn', 'crab', 'lobster'],
      'Sesame': ['sesame', 'til'],
    };
    final keywords = terms[allergy];
    if (keywords == null) return 'Unable to verify $allergy from the available data.';
    if (source.isEmpty) return 'Unable to verify $allergy because ingredient and allergen data are unavailable.';
    if (keywords.any(source.contains)) return 'Potential $allergy match found — check the package label before consuming.';
    return 'No $allergy match found in the available data; this is not an allergen-free guarantee.';
  }

  @override
  Widget build(BuildContext context) {
    if (!profile.hasInformation) return const SizedBox.shrink();
    final messages = <String>[];
    final source = _sourceText();
    final conditions = profile.conditions;
    if (conditions.contains('Diabetes')) {
      messages.add(_nutrient('sugar') == null
          ? 'Sugar information is unavailable for this product.'
          : 'For diabetes: total sugars are ${_nutrient('sugar')}; carbohydrates are ${_nutrient('total_carbohydrate') ?? 'unavailable'}.');
    }
    if (conditions.contains('High blood pressure (hypertension)')) {
      messages.add(_nutrient('sodium') == null && _nutrient('salt') == null
          ? 'Sodium and salt information is unavailable for this product.'
          : 'For high blood pressure: sodium is ${_nutrient('sodium') ?? 'unavailable'}; salt is ${_nutrient('salt') ?? 'unavailable'}.');
    }
    if (conditions.contains('High cholesterol') || conditions.contains('Heart-related condition')) {
      messages.add('Saturated fat: ${_nutrient('saturated_fat') ?? 'unavailable'}; trans fat: ${_nutrient('trans_fat') ?? 'unavailable'}.');
    }
    if (conditions.contains('Thyroid condition')) {
      messages.add('Thyroid condition noted. No product-specific warning is made without relevant verified product evidence.');
    }
    if (conditions.contains('Lactose intolerance') && source.isNotEmpty) {
      messages.add(_allergyStatus('Milk/dairy', source));
    }
    if (conditions.contains('Celiac disease') && source.isNotEmpty) {
      messages.add(_allergyStatus('Wheat/gluten', source));
    }
    for (final allergy in profile.allergies.where((item) => !{'Other', 'No known food allergies'}.contains(item))) {
      messages.add(_allergyStatus(allergy, source));
    }
    if (profile.preferences.contains('Vegan')) {
      messages.add(source.isEmpty
          ? 'Unable to verify vegan compatibility because ingredient data is unavailable.'
          : (['milk', 'egg', 'honey', 'gelatin', 'meat', 'fish'].any(source.contains)
              ? 'Potential non-vegan ingredient match found — verify the package label.'
              : 'No common non-vegan ingredient match found in the available data; verify the package label.'));
    }
    if (profile.preferences.contains('Vegetarian') || profile.preferences.contains('Eggetarian')) {
      messages.add(source.isEmpty
          ? 'Unable to verify dietary preference compatibility because ingredient data is unavailable.'
          : (['meat', 'chicken', 'beef', 'pork', 'fish', 'gelatin'].any(source.contains)
              ? 'Potential non-vegetarian ingredient match found — verify the package label.'
              : 'No common meat or fish ingredient match found in the available data; verify the package label.'));
    }
    if (profile.preferences.contains('Jain')) {
      messages.add(source.isEmpty
          ? 'Unable to verify Jain compatibility because ingredient data is unavailable.'
          : (['onion', 'garlic', 'potato', 'carrot'].any(source.contains)
              ? 'Potential Jain-preference ingredient match found — verify the package label.'
              : 'No common Jain-preference ingredient match found in the available data; verify the package label.'));
    }

    if (messages.isEmpty) {
      messages.add('No profile-specific checks were selected. Existing nutrition and score information is shown above.');
    }
    return Card(
      color: Theme.of(context).colorScheme.primaryContainer,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Personalized for You', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          const Text('These are informational checks, not medical advice or a safety guarantee.'),
          const SizedBox(height: 8),
          ...messages.map((message) => Padding(
            padding: const EdgeInsets.only(bottom: 6),
            child: Text('• $message'),
          )),
        ]),
      ),
    );
  }
}
