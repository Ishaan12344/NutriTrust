import 'package:flutter/material.dart';

/// AppTheme provides the complete Material 3 theming for NutriTrust.
/// It maintains backward compatibility with existing color constants while
/// also providing a proper ColorScheme derived from the primary seed color.
class AppTheme {
  AppTheme._();

  /// Seed color derived from the NutriTrust brand green.
  static const Color seedColor = Color(0xFF1B7A5A);

  /// Brand colors — kept for backward compatibility across the codebase.
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

  /// Linear gradients used throughout the app.
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

  /// NutriScore grade colors.
  static const Map<String, Color> nutriScoreColors = {
    'a': Color(0xFF038141),
    'b': Color(0xFF85BB2F),
    'c': Color(0xFFFECB02),
    'd': Color(0xFFEE8100),
    'e': Color(0xFFE63E11),
  };

  /// Traffic light colors.
  static const Color trafficGreen = Color(0xFF229954);
  static const Color trafficAmber = Color(0xFFF39C12);
  static const Color trafficRed = Color(0xFFE74C3C);

  /// Grade color based on NutriScore or custom grading system.
  /// Accepts single-letter grades (a-e) or full grade names.
  static Color gradeColor(String? grade) {
    if (grade == null) return textLight;
    final g = grade.toLowerCase();
    switch (g) {
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
        // Try parsing as numeric score
        try {
          final score = double.parse(g);
          return scoreColor(score);
        } catch (_) {
          return textLight;
        }
    }
  }

  /// Score color based on numeric value.
  static Color scoreColor(num? score) {
    if (score == null) return textLight;
    if (score >= 80) return const Color(0xFF038141);
    if (score >= 60) return const Color(0xFF85BB2F);
    if (score >= 40) return const Color(0xFFFECB02);
    if (score >= 20) return const Color(0xFFEE8100);
    return const Color(0xFFE63E11);
  }

  /// Traffic light color based on color string.
  static Color trafficLightColor(String? color) {
    if (color == null) return textLight;
    final c = color.toLowerCase();
    switch (c) {
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

  /// --- Light ColorScheme (Material 3, seed-derived) ---
  static final ColorScheme lightColorScheme = ColorScheme.fromSeed(
    seedColor: seedColor,
    brightness: Brightness.light,
    surface: surfaceWhite,
    surfaceContainer: const Color(0xFFF3F8F6),
    inverseSurface: const Color(0xFF212121),
    onSurface: textDark,
    onSurfaceVariant: textMedium,
  );

  /// --- Dark ColorScheme (Material 3, seed-derived) ---
  static final ColorScheme darkColorScheme = ColorScheme.fromSeed(
    seedColor: seedColor,
    brightness: Brightness.dark,
    surface: const Color(0xFF1A1A1A),
    surfaceContainer: const Color(0xFF252525),
    inverseSurface: const Color(0xFFE5E5E5),
    onSurface: Colors.white,
    onSurfaceVariant: Color(0xFFB0B0B0),
  );

  /// --- Light theme ---
  static ThemeData get lightTheme {
    return ThemeData(
      useMaterial3: true,
      colorScheme: lightColorScheme,
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
          side: BorderSide(color: lightColorScheme.outline, width: 1),
        ),
        clipBehavior: Clip.antiAlias,
        margin: EdgeInsets.zero,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: lightColorScheme.surfaceContainerHighest,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: lightColorScheme.outline),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: lightColorScheme.outline),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: primaryGreen, width: 2),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: errorColor),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: errorColor, width: 2),
        ),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        labelStyle: const TextStyle(color: textMedium),
        hintStyle: const TextStyle(color: textLight),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
          textStyle: const TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w600,
            letterSpacing: 0.3,
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
          side: BorderSide(color: primaryGreen.withValues(alpha: 0.5)),
          textStyle: const TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w500,
          ),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          textStyle: const TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w500,
          ),
        ),
      ),
      chipTheme: ChipThemeData(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
      ),
      dividerTheme: DividerThemeData(
        color: lightColorScheme.outline,
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

  /// --- Dark theme ---
  static ThemeData get darkTheme {
    return ThemeData(
      useMaterial3: true,
      colorScheme: darkColorScheme,
      scaffoldBackgroundColor: const Color(0xFF111111),
      appBarTheme: const AppBarTheme(
        elevation: 0,
        backgroundColor: Colors.transparent,
        foregroundColor: Colors.white,
        centerTitle: true,
        titleTextStyle: TextStyle(
          fontSize: 20,
          fontWeight: FontWeight.w600,
          color: Colors.white,
          letterSpacing: -0.3,
        ),
      ),
      cardTheme: CardThemeData(
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(color: darkColorScheme.outline, width: 1),
        ),
        clipBehavior: Clip.antiAlias,
        margin: EdgeInsets.zero,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: darkColorScheme.surfaceContainer,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: darkColorScheme.outline),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: darkColorScheme.outline),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: primaryGreen, width: 2),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: errorColor),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: errorColor, width: 2),
        ),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        labelStyle: const TextStyle(color: Color(0xFF8FA08F)),
        hintStyle: const TextStyle(color: Color(0xFF7A8D7A)),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
          textStyle: const TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w600,
            letterSpacing: 0.3,
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
          side: BorderSide(color: primaryGreen.withValues(alpha: 0.5)),
          textStyle: const TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w500,
          ),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          textStyle: const TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w500,
          ),
        ),
      ),
      chipTheme: ChipThemeData(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
      ),
      dividerTheme: DividerThemeData(
        color: darkColorScheme.outline,
        thickness: 1,
      ),
      textTheme: const TextTheme(
        headlineLarge: TextStyle(
          fontSize: 32,
          fontWeight: FontWeight.w700,
          letterSpacing: -0.5,
          color: Color(0xFFF5F5F5),
        ),
        headlineMedium: TextStyle(
          fontSize: 28,
          fontWeight: FontWeight.w700,
          letterSpacing: -0.3,
          color: Color(0xFFF5F5F5),
        ),
        headlineSmall: TextStyle(
          fontSize: 22,
          fontWeight: FontWeight.w600,
          letterSpacing: -0.2,
          color: Color(0xFFF5F5F5),
        ),
        titleLarge: TextStyle(
          fontSize: 20,
          fontWeight: FontWeight.w600,
          color: Color(0xFFF5F5F5),
        ),
        titleMedium: TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w600,
          color: Color(0xFFF5F5F5),
        ),
        titleSmall: TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w600,
          color: Color(0xFFF5F5F5),
        ),
        bodyLarge: TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w400,
          color: Color(0xFFB0B0B0),
          height: 1.5),
        bodyMedium: TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w400,
          color: Color(0xFFB0B0B0),
          height: 1.5),
        bodySmall: TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w400,
          color: Color(0xFF7A8D7A),
          height: 1.4),
        labelLarge: TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w600,
          color: Color(0xFFF5F5F5),
        ),
        labelMedium: TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w500,
          color: Color(0xFF8FA08F),
        ),
        labelSmall: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w500,
          color: Color(0xFF7A8D7A),
        ),
      ),
    );
  }
}