import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/screens/home_screen.dart';
import 'package:frontend/services/nutritrust_api_service.dart';
import 'package:frontend/widgets/ai_summary.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _analysis = {
  'product': {'name': 'Sample food'},
  'scoring': {
    'scores': {'overall': 48, 'grade': 'C'},
  },
};

NutriTrustApiService _serviceReturning(Future<http.Response> Function() respond) {
  return NutriTrustApiService(
    client: MockClient((_) => respond()),
    baseUrl: 'https://api.example.test',
  );
}

Future<void> _pumpCard(WidgetTester tester, NutriTrustApiService api) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: AiSummaryCard(api: api, response: _analysis, username: 'johndoe'),
        ),
      ),
    ),
  );
  // Let the summary future resolve and the card rebuild.
  await tester.pump();
  await tester.pump();
}

void main() {
  testWidgets('renders the model summary once it loads', (tester) async {
    final api = _serviceReturning(
      () async => http.Response(
        jsonEncode({'success': true, 'status': 'ok', 'summary': 'Summary from the model.'}),
        200,
      ),
    );

    await _pumpCard(tester, api);

    expect(find.text('AI Summary'), findsOneWidget);
    expect(find.text('Summary from the model.'), findsOneWidget);
    api.close();
  });

  testWidgets('shows a reason instead of an error when disabled', (tester) async {
    final api = _serviceReturning(
      () async => http.Response(
        jsonEncode({'success': false, 'status': 'disabled', 'summary': null}),
        200,
      ),
    );

    await _pumpCard(tester, api);

    expect(find.textContaining('turned off'), findsOneWidget);
    api.close();
  });

  testWidgets('degrades gracefully when the request fails', (tester) async {
    final api = _serviceReturning(
      () async => http.Response(jsonEncode({'detail': 'Server unavailable.'}), 503),
    );

    await _pumpCard(tester, api);

    expect(find.text('Server unavailable.'), findsOneWidget);
    api.close();
  });

  testWidgets(
    'a barcode with almost no data still shows every report section and a summary',
    (tester) async {
      // Mirrors what the backend returns when Open Food Facts has little or no
      // information for the scanned barcode.
      final response = <String, dynamic>{
        'success': true,
        'product_analysis': {
          'product': {'name': null, 'brands': null, 'barcode': '8901234567890'},
          'nutrition': {'per_100g': {}, 'per_serving': {}},
          'ingredients': {'text': null},
          'allergens': {
            'declared': <String>[],
            'declaration': null,
            'precautionary_traces': {'text': null},
          },
          'classification': {'nova_group': null},
          'scoring': {
            'scores': {'overall': null, 'grade': 'N/A'},
            'data_sufficiency': {'scoring_eligibility': 'ineligible'},
          },
          'health_analysis': {
            'findings': [
              {
                'id': 'nutrition.sugar',
                'severity': 'attention',
                'category': 'missing',
                'status': 'missing',
                'explanation': 'Sugar could not be assessed because no value was available.',
              },
            ],
          },
          'warnings': ['Product name is unavailable from Open Food Facts.'],
          'missing_data_warnings': [
            'nutrition per 100g is unavailable from Open Food Facts.'
          ],
        },
      };
      final api = _serviceReturning(
        () async => http.Response(
          jsonEncode({
            'success': true,
            'status': 'ok',
            'source': 'fallback',
            'summary': 'This product could not be scored because too little data was available.',
          }),
          200,
        ),
      );

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: NutritionReport(response: response, api: api, username: 'johndoe'),
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 900));

      // The summary is shown even though the data is poor.
      expect(find.text('AI Summary'), findsOneWidget);
      expect(find.textContaining('could not be scored'), findsOneWidget);

      // No report section silently disappears; empty ones say so instead.
      expect(find.text('Energy'), findsOneWidget);
      expect(find.text('Macronutrients'), findsOneWidget);
      expect(find.text('Other Nutrients'), findsOneWidget);
      expect(
        find.textContaining('Not available in the data found'),
        findsNWidgets(3),
      );

      // Findings, warnings and the unknown product name are still shown.
      expect(find.text('Not available'), findsWidgets);
      expect(
        find.textContaining('unavailable from Open Food Facts'),
        findsWidgets,
      );
      api.close();
    },
  );
}
