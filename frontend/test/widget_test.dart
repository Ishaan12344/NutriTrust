import 'package:flutter_test/flutter_test.dart';

import 'package:frontend/main.dart';
import 'package:frontend/screens/login_screen.dart';

void main() {
  testWidgets('app starts on the login screen', (WidgetTester tester) async {
    await tester.pumpWidget(const NutriTrustApp());
    await tester.pump();

    expect(find.byType(LoginScreen), findsOneWidget);
  });
}
