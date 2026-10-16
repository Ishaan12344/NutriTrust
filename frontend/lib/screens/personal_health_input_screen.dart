import 'package:flutter/material.dart';

import '../models/health_profile.dart';
import '../services/nutritrust_api_service.dart';
import '../theme/app_theme.dart';
import 'home_screen.dart';

class PersonalHealthInputScreen extends StatefulWidget {
  const PersonalHealthInputScreen(
      {super.key, this.initialProfile, this.username});

  final HealthProfile? initialProfile;
  final String? username;

  @override
  State<PersonalHealthInputScreen> createState() =>
      _PersonalHealthInputScreenState();
}

class _PersonalHealthInputScreenState
    extends State<PersonalHealthInputScreen> {
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
  late final TextEditingController _name;
  late final TextEditingController _weight;
  late final TextEditingController _allergyOther;
  late final TextEditingController _conditionOther;
  late Set<String> _allergies;
  late Set<String> _conditions;
  late Set<String> _preferences;
  String? _gender;
  String? _ageError;
  String? _weightError;
  final _api = NutriTrustApiService();

  @override
  void initState() {
    super.initState();
    final p = widget.initialProfile;
    _age = TextEditingController(text: p?.age?.toString() ?? '');
    _name = TextEditingController(text: p?.name ?? '');
    _weight = TextEditingController(
        text: p?.weight != null ? p!.weight.toString() : '');
    _allergyOther = TextEditingController(text: p?.allergyOther ?? '');
    _conditionOther = TextEditingController(text: p?.conditionOther ?? '');
    _allergies = {...?p?.allergies};
    _conditions = {...?p?.conditions};
    _preferences = {...?p?.preferences};
    _gender = p?.gender;
  }

  @override
  void dispose() {
    _age.dispose();
    _name.dispose();
    _weight.dispose();
    _allergyOther.dispose();
    _conditionOther.dispose();
    _api.close();
    super.dispose();
  }

  void _toggleAllergy(String value) {
    setState(() {
      if (value == 'No known food allergies') {
        _allergies = _allergies.contains(value) ? {} : {value};
      } else {
        _allergies.remove('No known food allergies');
        _allergies.contains(value)
            ? _allergies.remove(value)
            : _allergies.add(value);
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
        _conditions.contains(value)
            ? _conditions.remove(value)
            : _conditions.add(value);
      }
    });
  }

  void _togglePreference(String value) {
    setState(() {
      if (value == 'No specific dietary preference') {
        _preferences = _preferences.contains(value) ? {} : {value};
      } else {
        _preferences.remove('No specific dietary preference');
        _preferences.contains(value)
            ? _preferences.remove(value)
            : _preferences.add(value);
      }
    });
  }

  HealthProfile? _validatedProfile() {
    final rawAge = _age.text.trim();
    final age = rawAge.isEmpty ? null : int.tryParse(rawAge);
    if (rawAge.isNotEmpty && (age == null || age < 1 || age > 120)) {
      setState(
          () => _ageError = 'Enter an age from 1 to 120, or leave it blank.');
      return null;
    }
    setState(() => _ageError = null);

    final rawWeight = _weight.text.trim();
    final weight = rawWeight.isEmpty ? null : double.tryParse(rawWeight);
    if (rawWeight.isNotEmpty && (weight == null || weight < 1 || weight > 500)) {
      setState(() =>
          _weightError = 'Enter a valid weight in kg (1–500), or leave it blank.');
      return null;
    }
    setState(() => _weightError = null);

    final name = _name.text.trim();
    return HealthProfile(
      name: name.isEmpty ? null : name,
      age: age,
      weight: weight,
      gender: _gender,
      allergies: Set.unmodifiable(_allergies),
      allergyOther:
          _allergies.contains('Other') ? _allergyOther.text.trim() : null,
      conditions: Set.unmodifiable(_conditions),
      conditionOther:
          _conditions.contains('Other') ? _conditionOther.text.trim() : null,
      preferences: Set.unmodifiable(_preferences),
    );
  }

  void _continueToAnalysis({bool skip = false}) async {
    final profile = skip ? null : _validatedProfile();
    if (!skip && profile == null) return;

    if (widget.username != null && profile != null) {
      try {
        await _api.updateProfile(widget.username!, profile);
      } catch (_) {}
    }

    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(
        builder: (_) =>
            HomeScreen(profile: profile, username: widget.username),
      ),
      (route) => false,
    );
  }

  Widget _sectionCard({
    required IconData icon,
    required String title,
    required String subtitle,
    required List<Widget> children,
  }) {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: Colors.grey.shade200),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.03),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: AppTheme.primaryGreen.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(icon, color: AppTheme.primaryGreen, size: 22),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title,
                        style: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w700,
                            color: AppTheme.textDark)),
                    Text(subtitle,
                        style: const TextStyle(
                            fontSize: 12, color: AppTheme.textLight)),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          ...children,
        ],
      ),
    );
  }

  Widget _choiceGroup(
    String title,
    List<String> choices,
    Set<String> selected,
    ValueChanged<String> toggle,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title,
            style: const TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w500,
                color: AppTheme.textMedium)),
        const SizedBox(height: 8),
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: choices
              .map((c) => FilterChip(
                    label: Text(c, style: const TextStyle(fontSize: 12)),
                    selected: selected.contains(c),
                    onSelected: (_) => toggle(c),
                    selectedColor: AppTheme.primaryGreen.withOpacity(0.15),
                    checkmarkColor: AppTheme.primaryGreen,
                    side: BorderSide(
                      color: selected.contains(c)
                          ? AppTheme.primaryGreen.withOpacity(0.4)
                          : Colors.grey.shade300,
                    ),
                  ))
              .toList(),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: CustomScrollView(
        slivers: [
          SliverAppBar(
            expandedHeight: 140,
            pinned: true,
            backgroundColor: AppTheme.primaryGreen,
            foregroundColor: Colors.white,
            leading: widget.initialProfile == null
                ? null
                : IconButton(
                    icon: const Icon(Icons.arrow_back_rounded),
                    onPressed: () => Navigator.of(context).pop(),
                  ),
            flexibleSpace: FlexibleSpaceBar(
              background: Container(
                decoration: const BoxDecoration(gradient: AppTheme.headerGradient),
                child: SafeArea(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(20, 50, 20, 0),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'Your Health Profile',
                          style: TextStyle(
                            fontSize: 24,
                            fontWeight: FontWeight.w700,
                            color: Colors.white,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'Personalize your nutrition insights',
                          style: TextStyle(
                            fontSize: 14,
                            color: Colors.white.withOpacity(0.8),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
          SliverPadding(
            padding: const EdgeInsets.all(20),
            sliver: SliverList(
              delegate: SliverChildListDelegate([
                _sectionCard(
                  icon: Icons.person_outline_rounded,
                  title: 'Basic Information',
                  subtitle: 'All fields are optional',
                  children: [
                    TextField(
                      controller: _name,
                      decoration: const InputDecoration(
                        labelText: 'Full name',
                        prefixIcon: Icon(Icons.badge_outlined),
                      ),
                    ),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        Expanded(
                          child: TextField(
                            controller: _age,
                            keyboardType: TextInputType.number,
                            decoration: InputDecoration(
                              labelText: 'Age',
                              errorText: _ageError,
                              prefixIcon: const Icon(Icons.cake_outlined),
                            ),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: TextField(
                            controller: _weight,
                            keyboardType: const TextInputType.numberWithOptions(
                                decimal: true),
                            decoration: InputDecoration(
                              labelText: 'Weight (kg)',
                              errorText: _weightError,
                              prefixIcon:
                                  const Icon(Icons.monitor_weight_outlined),
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    DropdownButtonFormField<String>(
                      value: _gender,
                      decoration: const InputDecoration(
                        labelText: 'Gender',
                        prefixIcon: Icon(Icons.wc_outlined),
                      ),
                      items:
                          const ['Male', 'Female', 'Other', 'Prefer not to say']
                              .map((v) =>
                                  DropdownMenuItem(value: v, child: Text(v)))
                              .toList(),
                      onChanged: (v) => setState(() => _gender = v),
                    ),
                  ],
                ),
                _sectionCard(
                  icon: Icons.warning_amber_rounded,
                  title: 'Allergies & Intolerances',
                  subtitle: 'We’ll flag these in product scans',
                  children: [
                    _choiceGroup('Choose all that apply:', _allergyChoices,
                        _allergies, _toggleAllergy),
                    if (_allergies.contains('Other')) ...[
                      const SizedBox(height: 8),
                      TextField(
                        controller: _allergyOther,
                        decoration: const InputDecoration(
                            labelText: 'Other allergy or intolerance'),
                      ),
                    ],
                  ],
                ),
                _sectionCard(
                  icon: Icons.medical_services_outlined,
                  title: 'Health Conditions',
                  subtitle: 'Nutrient checks tailored to you',
                  children: [
                    _choiceGroup('Choose all that apply:', _conditionChoices,
                        _conditions, _toggleCondition),
                    if (_conditions.contains('Other')) ...[
                      const SizedBox(height: 8),
                      TextField(
                        controller: _conditionOther,
                        decoration: const InputDecoration(
                            labelText: 'Other health condition'),
                      ),
                    ],
                  ],
                ),
                _sectionCard(
                  icon: Icons.restaurant_outlined,
                  title: 'Dietary Preferences',
                  subtitle: 'Optional',
                  children: [
                    _choiceGroup('Choose all that apply:', _preferenceChoices,
                        _preferences, _togglePreference),
                  ],
                ),
                const SizedBox(height: 8),
                SizedBox(
                  height: 52,
                  child: FilledButton.icon(
                    onPressed: _continueToAnalysis,
                    icon: const Icon(Icons.arrow_forward_rounded),
                    label: const Text('Continue to Food Analysis',
                        style: TextStyle(
                            fontSize: 16, fontWeight: FontWeight.w600)),
                    style: FilledButton.styleFrom(
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14)),
                    ),
                  ),
                ),
                const SizedBox(height: 8),
                TextButton(
                  onPressed: () => _continueToAnalysis(skip: true),
                  child: const Text('Skip for now'),
                ),
                const SizedBox(height: 24),
              ]),
            ),
          ),
        ],
      ),
    );
  }
}
