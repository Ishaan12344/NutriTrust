class HealthProfile {
  const HealthProfile({
    this.name,
    this.age,
    this.weight,
    this.gender,
    this.allergies = const <String>{},
    this.allergyOther,
    this.conditions = const <String>{},
    this.conditionOther,
    this.preferences = const <String>{},
  });

  final String? name;
  final int? age;
  final double? weight;
  final String? gender;
  final Set<String> allergies;
  final String? allergyOther;
  final Set<String> conditions;
  final String? conditionOther;
  final Set<String> preferences;

  bool get hasInformation =>
      (name != null && name!.trim().isNotEmpty) ||
      age != null ||
      weight != null ||
      gender != null ||
      allergies.isNotEmpty ||
      conditions.isNotEmpty ||
      preferences.isNotEmpty;

  Map<String, dynamic> toJson() => {
    'name': name,
    'age': age,
    'weight': weight,
    'gender': gender,
    'allergies': allergies.toList(),
    'allergy_other': allergyOther,
    'conditions': conditions.toList(),
    'condition_other': conditionOther,
    'preferences': preferences.toList(),
  };

  factory HealthProfile.fromJson(Map<String, dynamic> json) {
    int? parsedAge;
    final rawAge = json['age'];
    if (rawAge is int) {
      parsedAge = rawAge;
    } else if (rawAge != null) {
      parsedAge = int.tryParse(rawAge.toString());
    }

    double? parsedWeight;
    final rawWeight = json['weight'];
    if (rawWeight is num) {
      parsedWeight = rawWeight.toDouble();
    } else if (rawWeight != null) {
      parsedWeight = double.tryParse(rawWeight.toString());
    }

    Set<String> toStringSet(dynamic value) {
      if (value is Iterable) {
        return value.map((e) => e.toString().trim()).where((s) => s.isNotEmpty).toSet();
      }
      return const <String>{};
    }

    return HealthProfile(
      name: json['name']?.toString(),
      age: parsedAge,
      weight: parsedWeight,
      gender: json['gender']?.toString(),
      allergies: toStringSet(json['allergies']),
      allergyOther: json['allergy_other']?.toString(),
      conditions: toStringSet(json['conditions']),
      conditionOther: json['condition_other']?.toString(),
      preferences: toStringSet(json['preferences']),
    );
  }

  HealthProfile copyWith({
    String? name,
    int? age,
    double? weight,
    String? gender,
    Set<String>? allergies,
    String? allergyOther,
    Set<String>? conditions,
    String? conditionOther,
    Set<String>? preferences,
  }) {
    return HealthProfile(
      name: name ?? this.name,
      age: age ?? this.age,
      weight: weight ?? this.weight,
      gender: gender ?? this.gender,
      allergies: allergies ?? this.allergies,
      allergyOther: allergyOther ?? this.allergyOther,
      conditions: conditions ?? this.conditions,
      conditionOther: conditionOther ?? this.conditionOther,
      preferences: preferences ?? this.preferences,
    );
  }
}
