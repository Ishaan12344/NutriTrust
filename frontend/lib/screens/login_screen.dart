import 'package:flutter/material.dart';

import '../models/health_profile.dart';
import '../services/nutritrust_api_service.dart';
import 'home_screen.dart';
import 'personal_health_input_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
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

  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();

  // Profile controllers for account creation
  final _nameController = TextEditingController();
  final _ageController = TextEditingController();
  final _weightController = TextEditingController();
  final _allergyOtherController = TextEditingController();
  final _conditionOtherController = TextEditingController();

  Set<String> _allergies = {};
  Set<String> _conditions = {};
  Set<String> _preferences = {};
  String? _gender;

  String? _ageError;
  String? _weightError;
  String? _errorMessage;

  bool _isSignUp = false;
  bool _isLoading = false;
  final _api = NutriTrustApiService();

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    _nameController.dispose();
    _ageController.dispose();
    _weightController.dispose();
    _allergyOtherController.dispose();
    _conditionOtherController.dispose();
    _api.close();
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

  HealthProfile? _buildProfileFromInputs() {
    final rawAge = _ageController.text.trim();
    final age = rawAge.isEmpty ? null : int.tryParse(rawAge);
    if (rawAge.isNotEmpty && (age == null || age < 1 || age > 120)) {
      setState(() => _ageError = 'Enter an age from 1 to 120, or leave it blank.');
      return null;
    }
    setState(() => _ageError = null);

    final rawWeight = _weightController.text.trim();
    final weight = rawWeight.isEmpty ? null : double.tryParse(rawWeight);
    if (rawWeight.isNotEmpty && (weight == null || weight < 1 || weight > 500)) {
      setState(() => _weightError = 'Enter a valid weight in kg (1 to 500), or leave it blank.');
      return null;
    }
    setState(() => _weightError = null);

    final name = _nameController.text.trim();

    return HealthProfile(
      name: name.isEmpty ? null : name,
      age: age,
      weight: weight,
      gender: _gender,
      allergies: Set.unmodifiable(_allergies),
      allergyOther: _allergies.contains('Other') ? _allergyOtherController.text.trim() : null,
      conditions: Set.unmodifiable(_conditions),
      conditionOther: _conditions.contains('Other') ? _conditionOtherController.text.trim() : null,
      preferences: Set.unmodifiable(_preferences),
    );
  }

  Future<void> _submit() async {
    final username = _usernameController.text.trim();
    final password = _passwordController.text;

    if (username.isEmpty || password.isEmpty) {
      setState(() => _errorMessage = 'Please enter both username/email and password.');
      return;
    }

    if (_isSignUp && password.length < 4) {
      setState(() => _errorMessage = 'Password must be at least 4 characters long.');
      return;
    }

    HealthProfile? profile;
    if (_isSignUp) {
      profile = _buildProfileFromInputs();
      if (profile == null) return; // Validation error in age or weight
    }

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      if (_isSignUp) {
        // Create account with full profile details in MongoDB
        await _api.register(
          username: username,
          password: password,
          profile: profile,
        );
        if (!mounted) return;

        // Skip guest page and go directly into the app
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(
            builder: (_) => HomeScreen(profile: profile, username: username),
          ),
        );
      } else {
        // Sign in with username/email and password
        final res = await _api.login(username: username, password: password);
        if (!mounted) return;

        HealthProfile userProfile = const HealthProfile();
        final rawUser = res['user'];
        if (rawUser is Map && rawUser['profile'] is Map) {
          userProfile = HealthProfile.fromJson(Map<String, dynamic>.from(rawUser['profile'] as Map));
        }

        // Skip guest page and go directly into the app
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(
            builder: (_) => HomeScreen(profile: userProfile, username: username),
          ),
        );
      }
    } on NutriTrustApiException catch (e) {
      if (mounted) setState(() => _errorMessage = e.message);
    } catch (e) {
      if (mounted) {
        setState(() => _errorMessage = 'Connection failed: please verify the backend and MongoDB connection.');
      }
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  void _skipToGuest() {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const PersonalHealthInputScreen()),
    );
  }

  Widget _choiceGroup(
    String title,
    String description,
    List<String> choices,
    Set<String> selected,
    ValueChanged<String> toggle,
  ) => Card(
    margin: const EdgeInsets.symmetric(vertical: 8),
    child: Padding(
      padding: const EdgeInsets.all(14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title, style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600)),
        const SizedBox(height: 2),
        Text(description, style: Theme.of(context).textTheme.bodySmall),
        const SizedBox(height: 8),
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: choices.map((choice) => FilterChip(
            label: Text(choice, style: const TextStyle(fontSize: 12)),
            selected: selected.contains(choice),
            onSelected: (_) => toggle(choice),
          )).toList(),
        ),
      ]),
    ),
  );

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 480),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Icon(
                    Icons.eco,
                    size: 56,
                    color: theme.colorScheme.primary,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'NutriTrust',
                    textAlign: TextAlign.center,
                    style: theme.textTheme.headlineMedium?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: theme.colorScheme.primary,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    _isSignUp
                        ? 'Create an account and setup your health & nutrition profile'
                        : 'Sign in to access your nutrition profile directly',
                    textAlign: TextAlign.center,
                    style: theme.textTheme.bodyMedium?.copyWith(color: Colors.grey[700]),
                  ),
                  const SizedBox(height: 24),
                  Card(
                    elevation: 1,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                    child: Padding(
                      padding: const EdgeInsets.all(20),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Text(
                            _isSignUp ? 'Create Account' : 'Sign In',
                            style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w600),
                          ),
                          const SizedBox(height: 16),
                          TextField(
                            controller: _usernameController,
                            autocorrect: false,
                            textCapitalization: TextCapitalization.none,
                            decoration: const InputDecoration(
                              labelText: 'Username or Email',
                              prefixIcon: Icon(Icons.person_outline),
                              border: OutlineInputBorder(),
                            ),
                          ),
                          const SizedBox(height: 14),
                          TextField(
                            controller: _passwordController,
                            obscureText: true,
                            decoration: const InputDecoration(
                              labelText: 'Password',
                              prefixIcon: Icon(Icons.lock_outline),
                              border: OutlineInputBorder(),
                            ),
                            onSubmitted: (_) {
                              if (!_isSignUp) _submit();
                            },
                          ),
                          if (_isSignUp) ...[
                            const SizedBox(height: 20),
                            const Divider(),
                            const SizedBox(height: 8),
                            Text(
                              'Personal Health Profile',
                              style: theme.textTheme.titleMedium?.copyWith(
                                fontWeight: FontWeight.bold,
                                color: theme.colorScheme.primary,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              'Provide your details to customize nutrition analysis:',
                              style: theme.textTheme.bodySmall,
                            ),
                            const SizedBox(height: 14),
                            TextField(
                              controller: _nameController,
                              decoration: const InputDecoration(
                                labelText: 'Full name (optional)',
                                prefixIcon: Icon(Icons.badge_outlined),
                                border: OutlineInputBorder(),
                              ),
                            ),
                            const SizedBox(height: 12),
                            Row(
                              children: [
                                Expanded(
                                  child: TextField(
                                    controller: _ageController,
                                    keyboardType: TextInputType.number,
                                    decoration: InputDecoration(
                                      labelText: 'Age (optional)',
                                      errorText: _ageError,
                                      border: const OutlineInputBorder(),
                                    ),
                                  ),
                                ),
                                const SizedBox(width: 12),
                                Expanded(
                                  child: TextField(
                                    controller: _weightController,
                                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                                    decoration: InputDecoration(
                                      labelText: 'Weight (kg, optional)',
                                      errorText: _weightError,
                                      border: const OutlineInputBorder(),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 12),
                            DropdownButtonFormField<String>(
                              value: _gender,
                              decoration: const InputDecoration(
                                labelText: 'Gender (optional)',
                                border: OutlineInputBorder(),
                              ),
                              items: const ['Male', 'Female', 'Other', 'Prefer not to say']
                                  .map((value) => DropdownMenuItem(value: value, child: Text(value)))
                                  .toList(),
                              onChanged: (value) => setState(() => _gender = value),
                            ),
                            const SizedBox(height: 12),
                            _choiceGroup(
                              'Allergies & Intolerances',
                              'Choose all that apply:',
                              _allergyChoices,
                              _allergies,
                              _toggleAllergy,
                            ),
                            if (_allergies.contains('Other')) Padding(
                              padding: const EdgeInsets.only(top: 4, bottom: 8),
                              child: TextField(
                                controller: _allergyOtherController,
                                decoration: const InputDecoration(
                                  labelText: 'Other allergy or intolerance',
                                  border: OutlineInputBorder(),
                                ),
                              ),
                            ),
                            _choiceGroup(
                              'Health Conditions',
                              'Choose all that apply:',
                              _conditionChoices,
                              _conditions,
                              _toggleCondition,
                            ),
                            if (_conditions.contains('Other')) Padding(
                              padding: const EdgeInsets.only(top: 4, bottom: 8),
                              child: TextField(
                                controller: _conditionOtherController,
                                decoration: const InputDecoration(
                                  labelText: 'Other health condition',
                                  border: OutlineInputBorder(),
                                ),
                              ),
                            ),
                            _choiceGroup(
                              'Dietary Preferences',
                              'Optional:',
                              _preferenceChoices,
                              _preferences,
                              _togglePreference,
                            ),
                          ],
                          if (_errorMessage != null) ...[
                            const SizedBox(height: 12),
                            Container(
                              padding: const EdgeInsets.all(10),
                              decoration: BoxDecoration(
                                color: Colors.red.shade50,
                                borderRadius: BorderRadius.circular(8),
                                border: Border.all(color: Colors.red.shade200),
                              ),
                              child: Text(
                                _errorMessage!,
                                style: TextStyle(color: Colors.red.shade900, fontSize: 13),
                              ),
                            ),
                          ],
                          const SizedBox(height: 20),
                          FilledButton(
                            onPressed: _isLoading ? null : _submit,
                            child: _isLoading
                                ? const SizedBox(
                                    height: 20,
                                    width: 20,
                                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                                  )
                                : Text(_isSignUp ? 'Create Account & Enter App' : 'Sign In'),
                          ),
                          const SizedBox(height: 10),
                          TextButton(
                            onPressed: () {
                              setState(() {
                                _isSignUp = !_isSignUp;
                                _errorMessage = null;
                              });
                            },
                            child: Text(
                              _isSignUp
                                  ? 'Already have an account? Sign In'
                                  : "Don't have an account? Create Account",
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextButton(
                    onPressed: _skipToGuest,
                    child: const Text('Continue as Guest'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
