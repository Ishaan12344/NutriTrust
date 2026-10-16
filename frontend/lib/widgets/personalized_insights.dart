import 'package:flutter/material.dart';

import '../models/health_profile.dart';
import '../theme/app_theme.dart';

class PersonalizedInsights extends StatelessWidget {
  const PersonalizedInsights(
      {super.key, required this.profile, required this.analysis});

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
    ]
        .where((item) => item != null)
        .map((item) => (item ?? '').toString().toLowerCase())
        .join(' ');
  }

  String _allergyStatus(String allergy, String source) {
    const terms = <String, List<String>>{
      'Peanuts': ['peanut', 'groundnut'],
      'Tree nuts': [
        'almond', 'cashew', 'walnut', 'pistachio', 'hazelnut', 'tree nut'
      ],
      'Milk/dairy': [
        'milk', 'dairy', 'lactose', 'casein', 'whey', 'butter', 'cheese'
      ],
      'Eggs': ['egg', 'albumin'],
      'Soy': ['soy', 'soya'],
      'Wheat/gluten': ['wheat', 'gluten', 'barley', 'rye'],
      'Fish': ['fish'],
      'Shellfish': [
        'shellfish', 'crustacean', 'shrimp', 'prawn', 'crab', 'lobster'
      ],
      'Sesame': ['sesame', 'til'],
    };
    final keywords = terms[allergy];
    if (keywords == null) {
      return 'Unable to verify $allergy from the available data.';
    }
    if (source.isEmpty) {
      return 'Unable to verify $allergy because ingredient and allergen data are unavailable.';
    }
    if (keywords.any(source.contains)) {
      return 'Potential $allergy match found — check the package label before consuming.';
    }
    return 'No $allergy match found in the available data; this is not an allergen-free guarantee.';
  }

  @override
  Widget build(BuildContext context) {
    if (!profile.hasInformation) return const SizedBox.shrink();

    final messages = <_InsightItem>[];
    final source = _sourceText();
    final conditions = profile.conditions;

    if (conditions.contains('Diabetes')) {
      messages.add(_InsightItem(
        icon: Icons.bloodtype_outlined,
        color: const Color(0xFFE53935),
        text: _nutrient('sugar') == null
            ? 'Sugar information is unavailable for this product.'
            : 'For diabetes: total sugars are ${_nutrient('sugar')}; carbohydrates are ${_nutrient('total_carbohydrate') ?? 'unavailable'}.',
      ));
    }
    if (conditions.contains('High blood pressure (hypertension)')) {
      messages.add(_InsightItem(
        icon: Icons.monitor_heart_outlined,
        color: const Color(0xFFD84315),
        text: _nutrient('sodium') == null && _nutrient('salt') == null
            ? 'Sodium and salt information is unavailable for this product.'
            : 'For high blood pressure: sodium is ${_nutrient('sodium') ?? 'unavailable'}; salt is ${_nutrient('salt') ?? 'unavailable'}.',
      ));
    }
    if (conditions.contains('High cholesterol') ||
        conditions.contains('Heart-related condition')) {
      messages.add(_InsightItem(
        icon: Icons.favorite_outline_rounded,
        color: const Color(0xFFAD1457),
        text:
            'Saturated fat: ${_nutrient('saturated_fat') ?? 'unavailable'}; trans fat: ${_nutrient('trans_fat') ?? 'unavailable'}.',
      ));
    }
    if (conditions.contains('Thyroid condition')) {
      messages.add(_InsightItem(
        icon: Icons.info_outline_rounded,
        color: const Color(0xFF1565C0),
        text:
            'Thyroid condition noted. No product-specific warning is made without relevant verified product evidence.',
      ));
    }
    if (conditions.contains('Lactose intolerance') && source.isNotEmpty) {
      final status = _allergyStatus('Milk/dairy', source);
      messages.add(_InsightItem(
        icon: status.contains('Potential')
            ? Icons.warning_amber_rounded
            : Icons.check_circle_outline,
        color: status.contains('Potential')
            ? const Color(0xFFE65100)
            : const Color(0xFF2E7D32),
        text: status,
      ));
    }
    if (conditions.contains('Celiac disease') && source.isNotEmpty) {
      final status = _allergyStatus('Wheat/gluten', source);
      messages.add(_InsightItem(
        icon: status.contains('Potential')
            ? Icons.warning_amber_rounded
            : Icons.check_circle_outline,
        color: status.contains('Potential')
            ? const Color(0xFFE65100)
            : const Color(0xFF2E7D32),
        text: status,
      ));
    }

    for (final allergy in profile.allergies
        .where((i) => !{'Other', 'No known food allergies'}.contains(i))) {
      final status = _allergyStatus(allergy, source);
      messages.add(_InsightItem(
        icon: status.contains('Potential')
            ? Icons.warning_amber_rounded
            : Icons.check_circle_outline,
        color: status.contains('Potential')
            ? const Color(0xFFE65100)
            : const Color(0xFF2E7D32),
        text: status,
      ));
    }

    if (profile.preferences.contains('Vegan')) {
      final isMatch = source.isNotEmpty &&
          ['milk', 'egg', 'honey', 'gelatin', 'meat', 'fish']
              .any(source.contains);
      messages.add(_InsightItem(
        icon: isMatch
            ? Icons.warning_amber_rounded
            : Icons.eco_outlined,
        color: source.isEmpty
            ? const Color(0xFF1565C0)
            : isMatch
                ? const Color(0xFFE65100)
                : const Color(0xFF2E7D32),
        text: source.isEmpty
            ? 'Unable to verify vegan compatibility because ingredient data is unavailable.'
            : isMatch
                ? 'Potential non-vegan ingredient match found — verify the package label.'
                : 'No common non-vegan ingredient match found in the available data; verify the package label.',
      ));
    }
    if (profile.preferences.contains('Vegetarian') ||
        profile.preferences.contains('Eggetarian')) {
      final isMatch = source.isNotEmpty &&
          ['meat', 'chicken', 'beef', 'pork', 'fish', 'gelatin']
              .any(source.contains);
      messages.add(_InsightItem(
        icon: isMatch
            ? Icons.warning_amber_rounded
            : Icons.restaurant_outlined,
        color: source.isEmpty
            ? const Color(0xFF1565C0)
            : isMatch
                ? const Color(0xFFE65100)
                : const Color(0xFF2E7D32),
        text: source.isEmpty
            ? 'Unable to verify dietary preference compatibility because ingredient data is unavailable.'
            : isMatch
                ? 'Potential non-vegetarian ingredient match found — verify the package label.'
                : 'No common meat or fish ingredient match found in the available data; verify the package label.',
      ));
    }
    if (profile.preferences.contains('Jain')) {
      final isMatch = source.isNotEmpty &&
          ['onion', 'garlic', 'potato', 'carrot'].any(source.contains);
      messages.add(_InsightItem(
        icon: isMatch ? Icons.warning_amber_rounded : Icons.spa_outlined,
        color: source.isEmpty
            ? const Color(0xFF1565C0)
            : isMatch
                ? const Color(0xFFE65100)
                : const Color(0xFF2E7D32),
        text: source.isEmpty
            ? 'Unable to verify Jain compatibility because ingredient data is unavailable.'
            : isMatch
                ? 'Potential Jain-preference ingredient match found — verify the package label.'
                : 'No common Jain-preference ingredient match found in the available data; verify the package label.',
      ));
    }

    if (messages.isEmpty) {
      messages.add(_InsightItem(
        icon: Icons.info_outline_rounded,
        color: AppTheme.primaryGreen,
        text:
            'No profile-specific checks were selected. Existing nutrition and score information is shown above.',
      ));
    }

    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            AppTheme.primaryGreen.withOpacity(0.06),
            AppTheme.accentTeal.withOpacity(0.06),
          ],
        ),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: AppTheme.primaryGreen.withOpacity(0.15)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: AppTheme.primaryGreen.withOpacity(0.12),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Icon(Icons.person_pin_outlined,
                    color: AppTheme.primaryGreen, size: 20),
              ),
              const SizedBox(width: 10),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Personalized for You',
                        style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w700,
                            color: AppTheme.textDark)),
                    Text('Based on your health profile',
                        style: TextStyle(
                            fontSize: 12, color: AppTheme.textLight)),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          ...messages.map((m) => Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      padding: const EdgeInsets.all(4),
                      decoration: BoxDecoration(
                        color: m.color.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Icon(m.icon, size: 16, color: m.color),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        m.text,
                        style: const TextStyle(
                            fontSize: 13, height: 1.4, color: AppTheme.textDark),
                      ),
                    ),
                  ],
                ),
              )),
          const SizedBox(height: 4),
          Text(
            'These are informational checks, not medical advice or a safety guarantee.',
            style: TextStyle(
                fontSize: 11,
                fontStyle: FontStyle.italic,
                color: Colors.grey.shade500),
          ),
        ],
      ),
    );
  }
}

class _InsightItem {
  const _InsightItem(
      {required this.icon, required this.color, required this.text});
  final IconData icon;
  final Color color;
  final String text;
}
