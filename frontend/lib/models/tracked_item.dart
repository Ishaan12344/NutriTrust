enum ConsumptionStatus {
  pending,
  eaten,
  notEaten;

  static ConsumptionStatus fromWire(String? value) {
    switch (value) {
      case 'eaten':
        return ConsumptionStatus.eaten;
      case 'not_eaten':
        return ConsumptionStatus.notEaten;
      default:
        return ConsumptionStatus.pending;
    }
  }

  String get wire => switch (this) {
        ConsumptionStatus.pending => 'pending',
        ConsumptionStatus.eaten => 'eaten',
        ConsumptionStatus.notEaten => 'not_eaten',
      };

  String get label => switch (this) {
        ConsumptionStatus.pending => 'Pending',
        ConsumptionStatus.eaten => 'Eaten',
        ConsumptionStatus.notEaten => 'Not eaten',
      };
}

Map<String, dynamic> _map(Object? value) =>
    value is Map ? Map<String, dynamic>.from(value) : <String, dynamic>{};

double? _number(Object? value) => value is num ? value.toDouble() : null;

List<String> _strings(Object? value) => value is Iterable
    ? value.map((e) => e.toString()).where((s) => s.trim().isNotEmpty).toList()
    : <String>[];

class TrackedItem {
  const TrackedItem({
    required this.id,
    required this.name,
    required this.date,
    required this.status,
    this.brand,
    this.barcode,
    this.imageUrl,
    this.nutriGrade,
    this.healthScore,
    this.manualName = false,
    this.needsName = false,
    this.partialData = false,
    this.consumedAt,
    this.nutrition = const <String, double>{},
    this.nutritionBasis = 'unknown',
    this.allergens = const <String>[],
    this.additives = const <String>[],
    this.missingFields = const <String>[],
  });

  final String id;
  final String name;
  final String date;
  final ConsumptionStatus status;
  final String? brand;
  final String? barcode;
  final String? imageUrl;
  final String? nutriGrade;
  final double? healthScore;
  final bool manualName;
  final bool needsName;
  final bool partialData;
  final DateTime? consumedAt;
  final Map<String, double> nutrition;
  final String nutritionBasis;
  final List<String> allergens;
  final List<String> additives;
  final List<String> missingFields;

  double get calories => nutrition['energy_kcal'] ?? 0;
  double get protein => nutrition['protein'] ?? 0;
  double get carbs => nutrition['total_carbohydrate'] ?? 0;
  double get fat => nutrition['total_fat'] ?? 0;
  double get sugar => nutrition['sugar'] ?? 0;
  double get sodium => nutrition['sodium'] ?? 0;
  double get fiber => nutrition['fiber'] ?? 0;

  factory TrackedItem.fromJson(Map<String, dynamic> json) {
    final rawNutrition = _map(json['nutrition']);
    return TrackedItem(
      id: json['item_id']?.toString() ?? '',
      name: json['name']?.toString() ?? 'Unnamed product',
      date: json['local_date']?.toString() ?? '',
      status: ConsumptionStatus.fromWire(json['status']?.toString()),
      brand: json['brand']?.toString(),
      barcode: json['barcode']?.toString(),
      imageUrl: json['image_url']?.toString(),
      nutriGrade: json['nutri_grade']?.toString(),
      healthScore: _number(json['health_score']),
      manualName: json['manual_name'] == true,
      needsName: json['needs_name'] == true,
      partialData: json['partial_data'] == true,
      consumedAt: DateTime.tryParse(json['consumed_at']?.toString() ?? '')?.toLocal(),
      nutrition: {
        for (final entry in rawNutrition.entries)
          if (entry.value is num) entry.key: (entry.value as num).toDouble(),
      },
      nutritionBasis: json['nutrition_basis']?.toString() ?? 'unknown',
      allergens: _strings(json['allergens']),
      additives: _strings(json['additives']),
      missingFields: _strings(json['missing_fields']),
    );
  }
}

class TrackerDay {
  const TrackerDay({
    required this.date,
    required this.totals,
    required this.eaten,
    required this.notEaten,
    required this.pending,
  });

  final String date;
  final Map<String, double> totals;
  final int eaten;
  final int notEaten;
  final int pending;

  double get calories => totals['energy_kcal'] ?? 0;

  factory TrackerDay.fromJson(Map<String, dynamic> json) {
    final rawTotals = _map(json['totals']);
    final counts = _map(json['counts']);
    return TrackerDay(
      date: json['date']?.toString() ?? '',
      totals: {
        for (final entry in rawTotals.entries)
          if (entry.value is num) entry.key: (entry.value as num).toDouble(),
      },
      eaten: (counts['eaten'] as num?)?.toInt() ?? 0,
      notEaten: (counts['not_eaten'] as num?)?.toInt() ?? 0,
      pending: (counts['pending'] as num?)?.toInt() ?? 0,
    );
  }
}

class TrackerRecommendation {
  const TrackerRecommendation({
    required this.type,
    required this.title,
    required this.message,
  });

  final String type;
  final String title;
  final String message;

  factory TrackerRecommendation.fromJson(Map<String, dynamic> json) =>
      TrackerRecommendation(
        type: json['type']?.toString() ?? 'info',
        title: json['title']?.toString() ?? '',
        message: json['message']?.toString() ?? '',
      );
}

class TrackerSnapshot {
  const TrackerSnapshot({
    required this.period,
    required this.rangeLabel,
    required this.items,
    required this.totals,
    required this.targets,
    required this.periodTargets,
    required this.percentages,
    required this.days,
    required this.trendDays,
    required this.recommendations,
    required this.eatenCount,
    required this.notEatenCount,
    required this.pendingCount,
    required this.partialDataCount,
    required this.highlight,
    required this.hasData,
  });

  final String period;
  final String rangeLabel;
  final List<TrackedItem> items;
  final Map<String, double> totals;
  final Map<String, double> targets;
  final Map<String, double> periodTargets;
  final Map<String, double> percentages;
  final List<TrackerDay> days;
  final List<TrackerDay> trendDays;
  final List<TrackerRecommendation> recommendations;
  final int eatenCount;
  final int notEatenCount;
  final int pendingCount;
  final int partialDataCount;
  final String highlight;
  final bool hasData;

  double get calories => totals['energy_kcal'] ?? 0;
  double get calorieTarget => periodTargets['energy_kcal'] ?? 0;
  double get caloriePercent => percentages['energy_kcal'] ?? 0;

  factory TrackerSnapshot.fromJson(Map<String, dynamic> json) {
    final rawTotals = _map(json['totals']);
    final rawTargets = _map(json['targets']);
    final rawPeriodTargets = _map(json['period_targets']);
    final rawPercentages = _map(json['percentages']);
    final counts = _map(json['counts']);
    final range = _map(json['range']);

    Map<String, double> numbers(Map<String, dynamic> source) => {
          for (final entry in source.entries)
            if (entry.value is num) entry.key: (entry.value as num).toDouble(),
        };

    return TrackerSnapshot(
      period: json['period']?.toString() ?? 'daily',
      rangeLabel: range['label']?.toString() ?? '',
      items: (json['items'] is List ? json['items'] as List : const [])
          .whereType<Map>()
          .map((item) => TrackedItem.fromJson(Map<String, dynamic>.from(item)))
          .toList(),
      totals: numbers(rawTotals),
      targets: numbers(rawTargets),
      periodTargets: numbers(rawPeriodTargets),
      percentages: numbers(rawPercentages),
      days: (json['days'] is List ? json['days'] as List : const [])
          .whereType<Map>()
          .map((day) => TrackerDay.fromJson(Map<String, dynamic>.from(day)))
          .toList(),
      trendDays: (json['trend_days'] is List ? json['trend_days'] as List : const [])
          .whereType<Map>()
          .map((day) => TrackerDay.fromJson(Map<String, dynamic>.from(day)))
          .toList(),
      recommendations: (json['recommendations'] is List
              ? json['recommendations'] as List
              : const [])
          .whereType<Map>()
          .map((rec) =>
              TrackerRecommendation.fromJson(Map<String, dynamic>.from(rec)))
          .toList(),
      eatenCount: (counts['eaten'] as num?)?.toInt() ?? 0,
      notEatenCount: (counts['not_eaten'] as num?)?.toInt() ?? 0,
      pendingCount: (counts['pending'] as num?)?.toInt() ?? 0,
      partialDataCount: (json['partial_data_count'] as num?)?.toInt() ?? 0,
      highlight: json['highlight']?.toString() ?? '',
      hasData: json['has_data'] == true,
    );
  }
}
