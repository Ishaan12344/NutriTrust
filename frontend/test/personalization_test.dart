import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/models/health_profile.dart';
import 'package:frontend/screens/personal_health_input_screen.dart';
import 'package:frontend/widgets/personalized_insights.dart';

void main() {
  testWidgets('invalid optional age is explained before continuing', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: PersonalHealthInputScreen()));

    await tester.enterText(find.byType(TextField).first, '0');
    await tester.tap(find.text('Continue to Food Analysis'));
    await tester.pump();

    expect(find.text('Enter an age from 1 to 120, or leave it blank.'), findsOneWidget);
  });

  testWidgets('personalized insights use product evidence and preserve uncertainty', (tester) async {
    const profile = HealthProfile(
      allergies: {'Milk/dairy'},
      conditions: {'Diabetes'},
      preferences: {'Vegan'},
    );
    final analysis = <String, dynamic>{
      'ingredients': {'text': 'Milk powder, sugar'},
      'allergens': {'declared': ['milk']},
      'nutrition': {
        'per_100g': {
          'sugar': {'value': 18, 'unit': 'g'},
          'total_carbohydrate': {'value': 40, 'unit': 'g'},
        },
      },
    };

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: PersonalizedInsights(profile: profile, analysis: analysis)),
    ));

    expect(find.text('Personalized for You'), findsOneWidget);
    expect(find.textContaining('Potential Milk/dairy match found'), findsOneWidget);
    expect(find.textContaining('total sugars are 18 g per 100 g'), findsOneWidget);
    expect(find.textContaining('Potential non-vegan ingredient match found'), findsOneWidget);
  });
}
