class HealthProfile {
  const HealthProfile({
    this.age,
    this.gender,
    this.allergies = const <String>{},
    this.allergyOther,
    this.conditions = const <String>{},
    this.conditionOther,
    this.preferences = const <String>{},
  });

  final int? age;
  final String? gender;
  final Set<String> allergies;
  final String? allergyOther;
  final Set<String> conditions;
  final String? conditionOther;
  final Set<String> preferences;

  bool get hasInformation =>
      age != null ||
      gender != null ||
      allergies.isNotEmpty ||
      conditions.isNotEmpty ||
      preferences.isNotEmpty;
}
