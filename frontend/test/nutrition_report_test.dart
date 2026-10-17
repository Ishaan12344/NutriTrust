import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/screens/home_screen.dart';
import 'package:frontend/services/nutritrust_api_service.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

/// Returns an API service whose summary call succeeds without a network, so the
/// report's AI summary card can render deterministically in widget tests.
NutriTrustApiService _stubSummaryApi() {
  final client = MockClient((request) async {
    if (request.url.path == '/api/v1/summary') {
      return http.Response(
        jsonEncode({
          'success': true,
          'status': 'ok',
          'summary': 'Model summary for the test.',
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    return http.Response('{}', 404);
  });
  return NutriTrustApiService(client: client);
}

void main() {
  testWidgets('barcode regression renders verified fields and omits absent nutrients', (tester) async {
    final response = <String, dynamic>{
      'product_analysis': {
        'product': {'name': 'Chitale Foods Instant Gulab Jamun Mix', 'brands': 'Chitale Foods', 'barcode': '8906002730018'},
        'nutrition': {
          'per_100g': {
            'energy_kcal': {'value': 431, 'unit': 'kcal', 'basis': 'per_100g', 'source': 'open_food_facts'},
            'total_fat': {'value': 14.6, 'unit': 'g', 'basis': 'per_100g', 'source': 'open_food_facts'},
            'saturated_fat': {'value': 8.2, 'unit': 'g', 'basis': 'per_100g', 'source': 'open_food_facts'},
            'total_carbohydrate': {'value': 54.6, 'unit': 'g', 'basis': 'per_100g', 'source': 'open_food_facts'},
            'sugar': {'value': 18.8, 'unit': 'g', 'basis': 'per_100g', 'source': 'open_food_facts'},
            'protein': {'value': 20.5, 'unit': 'g', 'basis': 'per_100g', 'source': 'open_food_facts'},
            'sodium': {'value': 414, 'unit': 'mg', 'basis': 'per_100g', 'source': 'open_food_facts'},
          },
          'per_serving': {},
        },
        'ingredients': {'text': 'Skimmed milk powder, refined wheat flour, hydrogenated vegetable oils, sodium bicarbonate'},
        'allergens': {'declared': <String>[], 'precautionary_traces': {'text': 'May contain nuts'}},
        'classification': {'nutriscore_grade': null, 'nova_group': 4, 'environmental_score_grade': null},
        'health_analysis': {'findings': <Object>[], 'ruleset': {'scope': 'Nutrient findings only'}},
        'scoring': {
          'formula_version': 'hybrid-v1',
          'weights': {'nutrient_quality': 0.4, 'nova_processing': 0.25, 'nutrient_limits': 0.2, 'additive_safety': 0.15},
          'component_scores': {'nutrient_quality': 50, 'nova_processing': 10, 'nutrient_limits': 50, 'additive_safety': 100},
          'contributions': {'nutrient_quality': 20, 'nova_processing': 2.5, 'nutrient_limits': 10, 'additive_safety': 15},
          'data_sufficiency': {'status': 'partial', 'missing': <String>[], 'nutrition': {'status': 'partial', 'missing_fields': ['added_sugar', 'serving_size']}, 'scoring_eligibility': 'eligible_provisional', 'score_confidence': 'not_calibrated'},
          'explanation': 'Provisional NutriTrust score.',
          'scores': {
            'overall': 48, 'grade': 'C', 'grade_label': 'Below average',
            'nutrient_quality': {'score': 50, 'details': 'Custom nutrient-quality component.'},
            'nova_processing': {'score': 10, 'nova_group': 4, 'source': 'open_food_facts', 'details': 'NOVA Group 4: Ultra-processed food product', 'markers_found': ['hydrogenated']},
            'nutrient_limits': {'score': 50, 'details': 'Solid food traffic-light results.', 'traffic_lights': {'sugar': {'value': 18.8, 'unit': 'g', 'color': 'amber', 'verified': true, 'thresholds': {'green': 5, 'amber': 22.5}}}},
            'additive_safety': {'score': 100, 'status': 'known', 'details': 'No configured concern match.', 'flagged_additives': <String>[]},
          },
        },
        'warnings': <String>[],
        'missing_data_warnings': <String>[],
      },
    };

    await tester.pumpWidget(MaterialApp(home: Scaffold(body: SingleChildScrollView(child: NutritionReport(response: response, api: _stubSummaryApi())))));
    await tester.pumpAndSettle();
    expect(find.text('Chitale Foods Instant Gulab Jamun Mix'), findsOneWidget);
    expect(find.textContaining('Per 100 g: 431 kcal'), findsOneWidget);
    expect(find.textContaining('Per 100 g: 20.5 g'), findsOneWidget);
    expect(find.text('Added sugars'), findsNothing);
    expect(find.textContaining('Per serving: Not available'), findsNothing);
    expect(find.textContaining('Nutrition completeness: partial'), findsOneWidget);
    expect(find.textContaining('Nutri-Score (reported)'), findsOneWidget);
  });

  testWidgets(
    'nutrition report renders values and analysis from API response',
    (WidgetTester tester) async {
      final response = <String, dynamic>{
        'success': true,
        'normalized_nutrition': {
          'serving_size': {'text': '40 g', 'weight_g': 40},
          'servings_per_container': 2,
          'reference_basis': {'detected': 'per_serving'},
          'whole_package': {'energy_kcal': 246, 'total_fat': 10},
        },
        'food_label': {
          'daily_values_percent': {'total_fat': 12},
          'nutrition_review': <Object>[],
        },
        'ocr': {'text': 'Product Name: Sample food'},
        'product_analysis': {
          'product': {
            'name': 'Sample food',
            'brands': 'Sample brand',
            'barcode': '0012345678905',
            'quantity': '80 g',
          },
          'identification': {
            'name': 'Sample food',
            'requested_barcode': '0012345678905',
          },
          'data_sources': {
            'product_name': 'ocr_label',
            'brands': 'ocr_label',
            'barcode': 'open_food_facts',
            'ingredients': 'ocr_label',
            'nutrition_per_100g': 'merged',
          },
          'ingredients': {
            'text': 'oats, sugar',
            'items': ['oats', 'sugar'],
            'source': 'ocr_label',
          },
          'allergens': {
            'label_analysis': {
              'declared': <String>[],
              'may_contain': <String>[],
              'ingredient_terms_detected': <String>[],
              'declaration_text': null,
              'precautionary_text': null,
            },
            'declared': <String>[],
            'declaration': null,
            'precautionary_traces': {'allergens': <String>[], 'text': null},
            'open_food_facts_tags': <String>[],
          },
          'nutrition': {
            'reference_basis': 'per_serving',
            'per_serving': {
              'energy_kcal': {
                'value': 123,
                'unit': 'kcal',
                'source': 'ocr_label',
              },
              'total_fat': {'value': 5, 'unit': 'g', 'source': 'ocr_label'},
            },
            'per_100g': {
              'energy_kcal': {
                'value': 307.5,
                'unit': 'kcal',
                'source': 'ocr_label',
              },
              'total_fat': {'value': 12.5, 'unit': 'g', 'source': 'ocr_label'},
            },
            'conflicts': <Object>[],
          },
          'classification': {
            'nova_group': 4,
            'nutriscore_grade': 'c',
            'environmental_score_grade': null,
            'additives_count': null,
            'additives_tags': <String>[],
          },
          'ocr': {'status': 'completed', 'extraction_status': 'completed'},
          'health_analysis': {
            'analysis_status': 'findings_available',
            'overall_score': null,
            'overall_score_status': 'not_calculated',
            'ruleset': {
              'id': 'uk_front_of_pack_food_thresholds',
              'version': '2016-guidance',
              'basis': 'per_100g',
              'scope':
                  'Nutrient bands only; not a whole-product health rating.',
            },
            'findings': [
              {
                'id': 'nutrition.total_fat',
                'type': 'nutrient_threshold',
                'status': 'known',
                'category': 'medium',
                'severity': 'informational',
                'measured': {
                  'value': 12.5,
                  'unit': 'g',
                  'basis': 'per_100g',
                  'source': 'ocr_label',
                },
                'explanation': 'The backend-assigned nutrient band.',
                'source': 'ocr_label',
              },
              {
                'id': 'classification.nutriscore_grade',
                'type': 'classification',
                'status': 'known',
                'category': 'reported_classification',
                'severity': 'informational',
                'measured': 'c',
                'explanation': 'Reported by Open Food Facts.',
                'source': 'open_food_facts',
              },
            ],
            'warnings': <String>[],
            'needs_review': false,
          },
          'conflicts': <Object>[],
          'warnings': <String>[],
          'missing_data_warnings': <String>[],
          'open_food_facts': {'request_status': 'not_requested'},
        },
      };

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: NutritionReport(response: response, api: _stubSummaryApi()),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Sample food'), findsOneWidget);
      expect(find.textContaining('Per serving: 123 kcal'), findsOneWidget);
      expect(find.textContaining('Per 100 g: 307.5 kcal'), findsOneWidget);
      expect(find.textContaining('Label DV: 12%'), findsOneWidget);
      expect(
        find.textContaining('Unknown — no declaration was identified'),
        findsOneWidget,
      );
      expect(find.textContaining('Reported Nutri-Score: c'), findsOneWidget);
      expect(
        find.textContaining('Nutrient observations and label findings'),
        findsOneWidget,
      );
      expect(find.textContaining('Not calculated by the backend'), findsNothing);
      expect(find.text('AI Summary'), findsOneWidget);
      expect(find.text('Model summary for the test.'), findsOneWidget);
    },
  );
}
