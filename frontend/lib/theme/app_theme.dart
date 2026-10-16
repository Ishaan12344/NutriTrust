import 'package:flutter/material.dart';

class AppTheme {
  AppTheme._();

  static const Color primaryGreen = Color(0xFF1B7A5A);
  static const Color primaryDark = Color(0xFF0D5A3E);
  static const Color primaryLight = Color(0xFF4CAF7D);
  static const Color accentTeal = Color(0xFF2EC4B6);
  static const Color accentAmber = Color(0xFFF4A261);
  static const Color bgLight = Color(0xFFF7FAF7);
  static const Color surfaceWhite = Color(0xFFFFFFFF);
  static const Color surfaceTint = Color(0xFFE8F5E9);
  static const Color textDark = Color(0xFF1A2E1A);
  static const Color textMedium = Color(0xFF4A5D4A);
  static const Color textLight = Color(0xFF7A8D7A);
  static const Color errorColor = Color(0xFFD84315);

  static const LinearGradient primaryGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [primaryDark, primaryGreen, accentTeal],
  );

  static const LinearGradient headerGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [primaryDark, primaryGreen],
  );

  static const Map<String, Color> nutriScoreColors = {
    'a': Color(0xFF038141),
    'b': Color(0xFF85BB2F),
    'c': Color(0xFFFECB02),
    'd': Color(0xFFEE8100),
    'e': Color(0xFFE63E11),
  };

  static const Color trafficGreen = Color(0xFF229954);
  static const Color trafficAmber = Color(0xFFF39C12);
  static const Color trafficRed = Color(0xFFE74C3C);

  static Color gradeColor(String? grade) {
    switch (grade?.toLowerCase()) {
      case 'a':
      case 'excellent':
        return const Color(0xFF038141);
      case 'b':
      case 'good':
        return const Color(0xFF85BB2F);
      case 'c':
      case 'average':
        return const Color(0xFFFECB02);
      case 'd':
      case 'below average':
        return const Color(0xFFEE8100);
      case 'e':
      case 'poor':
        return const Color(0xFFE63E11);
      default:
        return textLight;
    }
  }

  static Color scoreColor(num? score) {
    if (score == null) return textLight;
    if (score >= 80) return const Color(0xFF038141);
    if (score >= 60) return const Color(0xFF85BB2F);
    if (score >= 40) return const Color(0xFFFECB02);
    if (score >= 20) return const Color(0xFFEE8100);
    return const Color(0xFFE63E11);
  }

  static Color trafficLightColor(String? color) {
    switch (color?.toLowerCase()) {
      case 'green':
        return trafficGreen;
      case 'amber':
      case 'yellow':
        return trafficAmber;
      case 'red':
        return trafficRed;
      default:
        return textLight;
    }
  }

  static ThemeData get lightTheme {
    final colorScheme = ColorScheme.fromSeed(
      seedColor: primaryGreen,
      brightness: Brightness.light,
      primary: primaryGreen,
      onPrimary: Colors.white,
      primaryContainer: surfaceTint,
      secondary: accentTeal,
      tertiary: accentAmber,
      surface: surfaceWhite,
      error: errorColor,
    );

    return ThemeData(
      useMaterial3: true,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: bgLight,
      appBarTheme: const AppBarTheme(
        elevation: 0,
        scrolledUnderElevation: 2,
        backgroundColor: Colors.transparent,
        foregroundColor: textDark,
        centerTitle: true,
        titleTextStyle: TextStyle(
          fontSize: 20,
          fontWeight: FontWeight.w600,
          color: textDark,
          letterSpacing: -0.3,
        ),
      ),
      cardTheme: CardThemeData(
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(color: Colors.grey.shade200, width: 1),
        ),
        clipBehavior: Clip.antiAlias,
        margin: EdgeInsets.zero,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: Colors.grey.shade50,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: Colors.grey.shade300),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: Colors.grey.shade300),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: primaryGreen, width: 2),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: errorColor),
        ),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        labelStyle: const TextStyle(color: textMedium),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          textStyle: const TextStyle(
              fontSize: 16, fontWeight: FontWeight.w600, letterSpacing: 0.3),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          side: BorderSide(color: primaryGreen.withOpacity(0.5)),
          textStyle:
              const TextStyle(fontSize: 16, fontWeight: FontWeight.w500),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          textStyle:
              const TextStyle(fontSize: 14, fontWeight: FontWeight.w500),
        ),
      ),
      chipTheme: ChipThemeData(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
      ),
      dividerTheme: DividerThemeData(
        color: Colors.grey.shade200,
        thickness: 1,
      ),
      textTheme: const TextTheme(
        headlineLarge: TextStyle(
            fontSize: 32,
            fontWeight: FontWeight.w700,
            letterSpacing: -0.5,
            color: textDark),
        headlineMedium: TextStyle(
            fontSize: 26,
            fontWeight: FontWeight.w700,
            letterSpacing: -0.3,
            color: textDark),
        headlineSmall: TextStyle(
            fontSize: 22,
            fontWeight: FontWeight.w600,
            letterSpacing: -0.2,
            color: textDark),
        titleLarge: TextStyle(
            fontSize: 20, fontWeight: FontWeight.w600, color: textDark),
        titleMedium: TextStyle(
            fontSize: 16, fontWeight: FontWeight.w600, color: textDark),
        titleSmall: TextStyle(
            fontSize: 14, fontWeight: FontWeight.w600, color: textDark),
        bodyLarge: TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w400,
            color: textMedium,
            height: 1.5),
        bodyMedium: TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w400,
            color: textMedium,
            height: 1.5),
        bodySmall: TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w400,
            color: textLight,
            height: 1.4),
        labelLarge: TextStyle(
            fontSize: 14, fontWeight: FontWeight.w600, color: textDark),
        labelMedium: TextStyle(
            fontSize: 12, fontWeight: FontWeight.w500, color: textMedium),
        labelSmall: TextStyle(
            fontSize: 11, fontWeight: FontWeight.w500, color: textLight),
      ),
    );
  }
}
