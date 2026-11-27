import 'package:flutter/material.dart';

import '../models/health_profile.dart';
import '../services/nutritrust_api_service.dart';
import '../theme/app_theme.dart';
import 'home_screen.dart';
import 'personal_health_input_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen>
    with SingleTickerProviderStateMixin {
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
  bool _obscurePassword = true;
  final _api = NutriTrustApiService();

  late final AnimationController _fadeController;
  late final Animation<double> _fadeAnimation;

  @override
  void initState() {
    super.initState();
    _fadeController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    );
    _fadeAnimation = CurvedAnimation(
      parent: _fadeController,
      curve: Curves.easeOut,
    );
    _fadeController.forward();
  }

  @override
  void dispose() {
    _fadeController.dispose();
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

  HealthProfile? _buildProfileFromInputs() {
    final rawAge = _ageController.text.trim();
    final age = rawAge.isEmpty ? null : int.tryParse(rawAge);
    if (rawAge.isNotEmpty && (age == null || age < 1 || age > 120)) {
      setState(
          () => _ageError = 'Enter an age from 1 to 120, or leave it blank.');
      return null;
    }
    setState(() => _ageError = null);

    final rawWeight = _weightController.text.trim();
    final weight = rawWeight.isEmpty ? null : double.tryParse(rawWeight);
    if (rawWeight.isNotEmpty && (weight == null || weight < 1 || weight > 500)) {
      setState(() =>
          _weightError = 'Enter a valid weight in kg (1–500), or leave it blank.');
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
      allergyOther: _allergies.contains('Other')
          ? _allergyOtherController.text.trim()
          : null,
      conditions: Set.unmodifiable(_conditions),
      conditionOther: _conditions.contains('Other')
          ? _conditionOtherController.text.trim()
          : null,
      preferences: Set.unmodifiable(_preferences),
    );
  }

  Future<void> _submit() async {
    final username = _usernameController.text.trim();
    final password = _passwordController.text;

    if (username.isEmpty || password.isEmpty) {
      setState(
          () => _errorMessage = 'Please enter both username/email and password.');
      return;
    }
    if (_isSignUp && password.length < 4) {
      setState(
          () => _errorMessage = 'Password must be at least 4 characters long.');
      return;
    }

    HealthProfile? profile;
    if (_isSignUp) {
      profile = _buildProfileFromInputs();
      if (profile == null) return;
    }

    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      if (_isSignUp) {
        await _api.register(
            username: username, password: password, profile: profile);
        if (!mounted) return;
        Navigator.of(context).pushReplacement(MaterialPageRoute(
          builder: (_) => HomeScreen(profile: profile, username: username),
        ));
      } else {
        final res = await _api.login(username: username, password: password);
        if (!mounted) return;
        HealthProfile userProfile = const HealthProfile();
        final rawUser = res['user'];
        if (rawUser is Map && rawUser['profile'] is Map) {
          userProfile = HealthProfile.fromJson(
              Map<String, dynamic>.from(rawUser['profile'] as Map));
        }
        Navigator.of(context).pushReplacement(MaterialPageRoute(
          builder: (_) =>
              HomeScreen(profile: userProfile, username: username),
        ));
      }
    } on NutriTrustApiException catch (e) {
      if (mounted) setState(() => _errorMessage = e.message);
    } catch (_) {
      if (mounted) {
        setState(() => _errorMessage =
            'Connection failed: please verify the backend and MongoDB connection.');
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
  ) {
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 8),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.surfaceTint.withValues(alpha: 0.3),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppTheme.primaryGreen.withValues(alpha: 0.1)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title,
              style: const TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                  color: AppTheme.textDark)),
          const SizedBox(height: 2),
          Text(description,
              style:
                  const TextStyle(fontSize: 12, color: AppTheme.textLight)),
          const SizedBox(height: 10),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: choices
                .map((choice) => FilterChip(
                      label: Text(choice, style: const TextStyle(fontSize: 12)),
                      selected: selected.contains(choice),
                      onSelected: (_) => toggle(choice),
                      selectedColor:
                          AppTheme.primaryGreen.withValues(alpha: 0.15),
                      checkmarkColor: AppTheme.primaryGreen,
                      side: BorderSide(
                        color: selected.contains(choice)
                            ? AppTheme.primaryGreen.withValues(alpha: 0.4)
                            : Colors.grey.shade300,
                      ),
                    ))
                .toList(),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: FadeTransition(
        opacity: _fadeAnimation,
        child: Stack(
          children: [
            Container(
              height: MediaQuery.of(context).size.height * 0.38,
              decoration: const BoxDecoration(gradient: AppTheme.primaryGradient),
              child: SafeArea(
                child: Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: Colors.white.withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(20),
                        ),
                        child: const Icon(Icons.eco_rounded,
                            size: 48, color: Colors.white),
                      ),
                      const SizedBox(height: 16),
                      const Text(
                        'NutriTrust',
                        style: TextStyle(
                          fontSize: 32,
                          fontWeight: FontWeight.w800,
                          color: Colors.white,
                          letterSpacing: -0.5,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        'Eat with clarity',
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w400,
                          color: Colors.white.withValues(alpha: 0.85),
                          letterSpacing: 1,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
            SafeArea(
              child: SingleChildScrollView(
                padding: EdgeInsets.only(
                  top: MediaQuery.of(context).size.height * 0.28,
                  left: 20,
                  right: 20,
                  bottom: 32,
                ),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 480),
                  child: Column(
                    children: [
                      Container(
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(24),
                          boxShadow: [
                            BoxShadow(
                              color: Colors.black.withValues(alpha: 0.08),
                              blurRadius: 24,
                              offset: const Offset(0, 8),
                            ),
                          ],
                        ),
                        padding: const EdgeInsets.all(24),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Row(
                              children: [
                                Expanded(
                                  child: GestureDetector(
                                    onTap: () => setState(() {
                                      _isSignUp = false;
                                      _errorMessage = null;
                                    }),
                                    child: AnimatedContainer(
                                      duration:
                                          const Duration(milliseconds: 250),
                                      padding: const EdgeInsets.symmetric(
                                          vertical: 12),
                                      decoration: BoxDecoration(
                                        color: !_isSignUp
                                            ? AppTheme.primaryGreen
                                            : Colors.grey.shade100,
                                        borderRadius:
                                            BorderRadius.circular(12),
                                      ),
                                      alignment: Alignment.center,
                                      child: Text(
                                        'Sign In',
                                        style: TextStyle(
                                          fontSize: 15,
                                          fontWeight: FontWeight.w600,
                                          color: !_isSignUp
                                              ? Colors.white
                                              : AppTheme.textMedium,
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                                const SizedBox(width: 10),
                                Expanded(
                                  child: GestureDetector(
                                    onTap: () => setState(() {
                                      _isSignUp = true;
                                      _errorMessage = null;
                                    }),
                                    child: AnimatedContainer(
                                      duration:
                                          const Duration(milliseconds: 250),
                                      padding: const EdgeInsets.symmetric(
                                          vertical: 12),
                                      decoration: BoxDecoration(
                                        color: _isSignUp
                                            ? AppTheme.primaryGreen
                                            : Colors.grey.shade100,
                                        borderRadius:
                                            BorderRadius.circular(12),
                                      ),
                                      alignment: Alignment.center,
                                      child: Text(
                                        'Sign Up',
                                        style: TextStyle(
                                          fontSize: 15,
                                          fontWeight: FontWeight.w600,
                                          color: _isSignUp
                                              ? Colors.white
                                              : AppTheme.textMedium,
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 24),
                            TextField(
                              controller: _usernameController,
                              autocorrect: false,
                              textCapitalization: TextCapitalization.none,
                              decoration: const InputDecoration(
                                labelText: 'Username or Email',
                                prefixIcon: Icon(Icons.person_outline_rounded),
                              ),
                            ),
                            const SizedBox(height: 14),
                            TextField(
                              controller: _passwordController,
                              obscureText: _obscurePassword,
                              decoration: InputDecoration(
                                labelText: 'Password',
                                prefixIcon:
                                    const Icon(Icons.lock_outline_rounded),
                                suffixIcon: IconButton(
                                  icon: Icon(_obscurePassword
                                      ? Icons.visibility_off_outlined
                                      : Icons.visibility_outlined),
                                  onPressed: () => setState(
                                      () => _obscurePassword = !_obscurePassword),
                                ),
                              ),
                              onSubmitted: (_) {
                                if (!_isSignUp) _submit();
                              },
                            ),
                            AnimatedSize(
                              duration: const Duration(milliseconds: 350),
                              curve: Curves.easeInOut,
                              child: _isSignUp
                                  ? _buildSignUpFields()
                                  : const SizedBox.shrink(),
                            ),
                            if (_errorMessage != null) ...[
                              const SizedBox(height: 14),
                              Container(
                                padding: const EdgeInsets.all(12),
                                decoration: BoxDecoration(
                                  color: Colors.red.shade50,
                                  borderRadius: BorderRadius.circular(12),
                                  border:
                                      Border.all(color: Colors.red.shade200),
                                ),
                                child: Row(
                                  children: [
                                    Icon(Icons.error_outline,
                                        color: Colors.red.shade700, size: 20),
                                    const SizedBox(width: 8),
                                    Expanded(
                                      child: Text(
                                        _errorMessage!,
                                        style: TextStyle(
                                            color: Colors.red.shade900,
                                            fontSize: 13),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                            const SizedBox(height: 20),
                            SizedBox(
                              height: 52,
                              child: FilledButton(
                                onPressed: _isLoading ? null : _submit,
                                style: FilledButton.styleFrom(
                                  shape: RoundedRectangleBorder(
                                      borderRadius:
                                          BorderRadius.circular(14)),
                                ),
                                child: _isLoading
                                    ? const SizedBox(
                                        height: 22,
                                        width: 22,
                                        child: CircularProgressIndicator(
                                            strokeWidth: 2.5,
                                            color: Colors.white),
                                      )
                                    : Text(
                                        _isSignUp
                                            ? 'Create Account'
                                            : 'Sign In',
                                        style: const TextStyle(
                                            fontSize: 16,
                                            fontWeight: FontWeight.w600),
                                      ),
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 20),
                      TextButton.icon(
                        onPressed: _skipToGuest,
                        icon: const Icon(Icons.arrow_forward_rounded, size: 18),
                        label: const Text('Continue as Guest',
                            style: TextStyle(fontSize: 15)),
                      ),
                      const SizedBox(height: 16),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSignUpFields() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 20),
        Container(
          height: 1,
          color: Colors.grey.shade200,
        ),
        const SizedBox(height: 16),
        Row(
          children: [
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: AppTheme.primaryGreen.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(10),
              ),
              child: const Icon(Icons.favorite_outline_rounded,
                  color: AppTheme.primaryGreen, size: 20),
            ),
            const SizedBox(width: 10),
            const Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Health Profile',
                      style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                          color: AppTheme.textDark)),
                  Text('Personalize your nutrition insights',
                      style:
                          TextStyle(fontSize: 12, color: AppTheme.textLight)),
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        TextField(
          controller: _nameController,
          decoration: const InputDecoration(
            labelText: 'Full name (optional)',
            prefixIcon: Icon(Icons.badge_outlined),
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
                  labelText: 'Age',
                  errorText: _ageError,
                  prefixIcon: const Icon(Icons.cake_outlined),
                ),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: TextField(
                controller: _weightController,
                keyboardType:
                    const TextInputType.numberWithOptions(decimal: true),
                decoration: InputDecoration(
                  labelText: 'Weight (kg)',
                  errorText: _weightError,
                  prefixIcon: const Icon(Icons.monitor_weight_outlined),
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          initialValue: _gender,
          decoration: const InputDecoration(
            labelText: 'Gender (optional)',
            prefixIcon: Icon(Icons.wc_outlined),
          ),
          items: const ['Male', 'Female', 'Other', 'Prefer not to say']
              .map((v) => DropdownMenuItem(value: v, child: Text(v)))
              .toList(),
          onChanged: (v) => setState(() => _gender = v),
        ),
        const SizedBox(height: 8),
        _choiceGroup('Allergies & Intolerances', 'Choose all that apply:',
            _allergyChoices, _allergies, _toggleAllergy),
        if (_allergies.contains('Other'))
          Padding(
            padding: const EdgeInsets.only(top: 4, bottom: 8),
            child: TextField(
              controller: _allergyOtherController,
              decoration: const InputDecoration(
                  labelText: 'Other allergy or intolerance'),
            ),
          ),
        _choiceGroup('Health Conditions', 'Choose all that apply:',
            _conditionChoices, _conditions, _toggleCondition),
        if (_conditions.contains('Other'))
          Padding(
            padding: const EdgeInsets.only(top: 4, bottom: 8),
            child: TextField(
              controller: _conditionOtherController,
              decoration:
                  const InputDecoration(labelText: 'Other health condition'),
            ),
          ),
        _choiceGroup('Dietary Preferences', 'Optional:', _preferenceChoices,
            _preferences, _togglePreference),
      ],
    );
  }
}
