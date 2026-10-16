import 'package:flutter/material.dart';

import '../models/health_profile.dart';
import 'home_screen.dart';

class PersonalHealthInputScreen extends StatefulWidget {
  const PersonalHealthInputScreen({super.key, this.initialProfile});

  final HealthProfile? initialProfile;

  @override
  State<PersonalHealthInputScreen> createState() =>
      _PersonalHealthInputScreenState();
}

class _PersonalHealthInputScreenState extends State<PersonalHealthInputScreen> {
  static const _allergyChoices = [
    'Peanuts', 'Tree nuts', 'Milk/dairy', 'Eggs', 'Soy', 'Wheat/gluten',
    'Fish', 'Shellfish', 'Sesame', 'Other', 'No known food allergies',
  ];
  static const _conditionChoices = [
    'Diabetes', 'High blood pressure (hypertension)', 'Thyroid condition',
    'High cholesterol', 'Heart-related condition', 'Kidney-related condition',
    'Celiac disease', 'Lactose intolerance', 'Other', 'None of the above',
    'Prefer not to say',
  ];
  static const _preferenceChoices = [
    'Vegetarian', 'Vegan', 'Eggetarian', 'Jain',
    'No specific dietary preference', 'Other',
  ];

  late final TextEditingController _age;
  late final TextEditingController _allergyOther;
  late final TextEditingController _conditionOther;
  late Set<String> _allergies;
  late Set<String> _conditions;
  late Set<String> _preferences;
  String? _gender;
  String? _ageError;

  @override
  void initState() {
    super.initState();
    final profile = widget.initialProfile;
    _age = TextEditingController(text: profile?.age?.toString() ?? '');
    _allergyOther = TextEditingController(text: profile?.allergyOther ?? '');
    _conditionOther = TextEditingController(text: profile?.conditionOther ?? '');
    _allergies = {...?profile?.allergies};
    _conditions = {...?profile?.conditions};
    _preferences = {...?profile?.preferences};
    _gender = profile?.gender;
  }

  @override
  void dispose() {
    _age.dispose();
    _allergyOther.dispose();
    _conditionOther.dispose();
    super.dispose();
  }

  void _toggleAllergy(String value) {
    setState(() {
      if (value == 'No known food allergies') {
        _allergies = _allergies.contains(value) ? {} : {value};
      } else {
        _allergies.remove('No known food allergies');
        _allergies.contains(value) ? _allergies.remove(value) : _allergies.add(value);
      }
    });
  }

  void _toggleCondition(String value) {
    const exclusive = {'None of the above', 'Prefer not to say'};
    setState(() {
      if (exclusive.contains(value)) {
        _conditions = _conditions.contains(value) ? {} : {value};
      } else {
        _conditions.removeAll(exclusive);
        _conditions.contains(value) ? _conditions.remove(value) : _conditions.add(value);
      }
    });
  }

  void _togglePreference(String value) {
    setState(() {
      if (value == 'No specific dietary preference') {
        _preferences = _preferences.contains(value) ? {} : {value};
      } else {
        _preferences.remove('No specific dietary preference');
        _preferences.contains(value) ? _preferences.remove(value) : _preferences.add(value);
      }
    });
  }

  HealthProfile? _validatedProfile() {
    final rawAge = _age.text.trim();
    final age = rawAge.isEmpty ? null : int.tryParse(rawAge);
    if (rawAge.isNotEmpty && (age == null || age < 1 || age > 120)) {
      setState(() => _ageError = 'Enter an age from 1 to 120, or leave it blank.');
      return null;
    }
    setState(() => _ageError = null);
    return HealthProfile(
      age: age,
      gender: _gender,
      allergies: Set.unmodifiable(_allergies),
      allergyOther: _allergies.contains('Other') ? _allergyOther.text.trim() : null,
      conditions: Set.unmodifiable(_conditions),
      conditionOther: _conditions.contains('Other') ? _conditionOther.text.trim() : null,
      preferences: Set.unmodifiable(_preferences),
    );
  }

  void _continueToAnalysis({bool skip = false}) {
    final profile = skip ? null : _validatedProfile();
    if (!skip && profile == null) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => HomeScreen(profile: profile)),
      (route) => false,
    );
  }

  Widget _choiceGroup(
    String title,
    String description,
    List<String> choices,
    Set<String> selected,
    ValueChanged<String> toggle,
  ) => Card(
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title, style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 4),
        Text(description),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: choices.map((choice) => FilterChip(
            label: Text(choice),
            selected: selected.contains(choice),
            onSelected: (_) => toggle(choice),
          )).toList(),
        ),
      ]),
    ),
  );

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('Personalize Your Nutrition'),
      leading: widget.initialProfile == null ? null : BackButton(onPressed: () => Navigator.of(context).pop()),
    ),
    body: SafeArea(
      child: ListView(padding: const EdgeInsets.all(20), children: [
        Text('Tell us a little about your dietary needs to get food insights tailored to you.', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 20),
        Card(child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('Basic information', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 12),
            TextField(
              controller: _age,
              keyboardType: TextInputType.number,
              decoration: InputDecoration(labelText: 'Age (optional)', errorText: _ageError, border: const OutlineInputBorder()),
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              value: _gender,
              decoration: const InputDecoration(labelText: 'Gender (optional)', border: OutlineInputBorder()),
              items: const ['Male', 'Female', 'Other', 'Prefer not to say']
                  .map((value) => DropdownMenuItem(value: value, child: Text(value))).toList(),
              onChanged: (value) => setState(() => _gender = value),
            ),
          ]),
        )),
        const SizedBox(height: 12),
        _choiceGroup('Allergies and intolerances', 'Choose all that apply.', _allergyChoices, _allergies, _toggleAllergy),
        if (_allergies.contains('Other')) Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: TextField(controller: _allergyOther, decoration: const InputDecoration(labelText: 'Other allergy or intolerance', border: OutlineInputBorder())),
        ),
        _choiceGroup('Health conditions', 'Choose all that apply.', _conditionChoices, _conditions, _toggleCondition),
        if (_conditions.contains('Other')) Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: TextField(controller: _conditionOther, decoration: const InputDecoration(labelText: 'Other health condition', border: OutlineInputBorder())),
        ),
        _choiceGroup('Dietary preferences', 'Optional; choose all that apply.', _preferenceChoices, _preferences, _togglePreference),
        const SizedBox(height: 12),
        FilledButton(onPressed: _continueToAnalysis, child: const Text('Continue to Food Analysis')),
        TextButton(onPressed: () => _continueToAnalysis(skip: true), child: const Text('Skip for now')),
      ]),
    ),
  );
}
