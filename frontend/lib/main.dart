import 'package:flutter/material.dart';
import 'package:openfoodfacts/openfoodfacts.dart';

import 'screens/home_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();

  OpenFoodAPIConfiguration.userAgent = UserAgent(name: 'NutriTrust');

  OpenFoodAPIConfiguration.globalLanguages = [OpenFoodFactsLanguage.ENGLISH];

  runApp(const NutriTrustApp());
}

class NutriTrustApp extends StatelessWidget {
  const NutriTrustApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'NutriTrust',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF287D5A)),
        scaffoldBackgroundColor: const Color(0xFFF8FAF8),
        appBarTheme: const AppBarTheme(backgroundColor: Color(0xFFF8FAF8)),
      ),
      home: const HomeScreen(),
    );
  }
}
