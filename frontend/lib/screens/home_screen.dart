import 'dart:async';
import 'dart:developer' as developer;
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../models/health_profile.dart';
import '../services/nutritrust_api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/ai_summary.dart';
import '../widgets/nutrient_bar.dart';
import '../widgets/personalized_insights.dart';
import '../widgets/score_ring.dart';
import '../widgets/additive_card.dart';
import 'barcode_scanner_screen.dart';
import 'personal_health_input_screen.dart';
import 'tracker_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, this.profile, this.username});

  final HealthProfile? profile;
  final String? username;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final ImagePicker _picker = ImagePicker();
  final NutriTrustApiService _api = NutriTrustApiService();
  XFile? _selectedImage;
  Uint8List? _imageBytes;
  XFile? _ingredientsImage;
  Uint8List? _ingredientsBytes;
  Map<String, dynamic>? _analysis;
  bool _isLoading = false;
  String? _error;

  @override
  void dispose() {
    _api.close();
    super.dispose();
  }

  Future<void> _pickImage(
    ImageSource source, {
    bool ingredients = false,
  }) async {
    try {
      final image = await _picker.pickImage(source: source, imageQuality: 90);
      developer.log(
        'image picker returned: ${image?.name ?? 'cancelled'} '
        'target=${ingredients ? 'ingredients' : 'nutrition'}',
        name: 'nutritrust.ui',
      );
      if (image == null || !mounted) return;

      final bytes = await image.readAsBytes();
      developer.log(
        'image selected: name=${image.name} size=${bytes.length} type=${image.mimeType ?? 'unknown'}',
        name: 'nutritrust.ui',
      );
      if (bytes.length > 10 * 1024 * 1024) {
        setState(() => _error = 'Choose an image that is 10 MB or smaller.');
        return;
      }
      final extension = image.name.toLowerCase().split('.').last;
      if (!{'jpg', 'jpeg', 'png'}.contains(extension)) {
        setState(() => _error = 'Upload a JPG, JPEG, or PNG image.');
        return;
      }
      setState(() {
        if (ingredients) {
          _ingredientsImage = image;
          _ingredientsBytes = bytes;
        } else {
          _selectedImage = image;
          _imageBytes = bytes;
          _ingredientsImage = null;
          _ingredientsBytes = null;
        }
        _analysis = null;
        _error = null;
      });
    } catch (e, stackTrace) {
      developer.log(
        'image pick error',
        name: 'nutritrust.ui',
        error: e,
        stackTrace: stackTrace,
      );
      if (mounted) setState(() => _error = 'Unable to select that image.');
    }
  }

  Future<void> _pickIngredients() async {
    final source = await showModalBottomSheet<ImageSource>(
      context: context,
      builder: (sheetContext) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.camera_alt_rounded),
              title: const Text('Take ingredients photo'),
              onTap: () => Navigator.pop(sheetContext, ImageSource.camera),
            ),
            ListTile(
              leading: const Icon(Icons.photo_library_rounded),
              title: const Text('Choose ingredients image'),
              onTap: () => Navigator.pop(sheetContext, ImageSource.gallery),
            ),
          ],
        ),
      ),
    );
    if (source != null) await _pickImage(source, ingredients: true);
  }

  String _contentTypeFor(String? name) =>
      (name ?? '').toLowerCase().endsWith('.png') ? 'image/png' : 'image/jpeg';

  Future<void> _analyzeImage() async {
    final image = _selectedImage;
    final bytes = _imageBytes;
    if (image == null || bytes == null || _isLoading) return;
    developer.log(
      'label callback triggered; api=${_api.baseUrl}',
      name: 'nutritrust.ui',
    );
    setState(() {
      _isLoading = true;
      _error = null;
    });
    try {
      final name = image.name;
      final ingredientsName = _ingredientsImage?.name;
      final response = await _api.analyzeLabel(
        imageBytes: bytes,
        filename: name,
        contentType: _contentTypeFor(name),
        ingredientsImageBytes: _ingredientsBytes,
        ingredientsFilename: ingredientsName,
        ingredientsContentType: ingredientsName == null
            ? null
            : _contentTypeFor(ingredientsName),
        username: widget.username,
      );
      if (!mounted) return;
      setState(() => _analysis = response);
      unawaited(_trackAnalysis(response));
    } on NutriTrustApiException catch (error) {
      developer.log('label UI error', name: 'nutritrust.ui', error: error);
      if (mounted) setState(() => _error = error.message);
    } catch (error, stackTrace) {
      developer.log(
        'label unexpected UI error',
        name: 'nutritrust.ui',
        error: error,
        stackTrace: stackTrace,
      );
      if (mounted) {
        setState(
          () => _error = 'The label could not be analyzed. Please retry.',
        );
      }
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  Future<void> _scanBarcode() async {
    developer.log(
      'barcode button triggered; api=${_api.baseUrl}',
      name: 'nutritrust.ui',
    );
    if (mounted) {
      setState(() {
        _selectedImage = null;
        _imageBytes = null;
        _ingredientsImage = null;
        _ingredientsBytes = null;
        _error = null;
      });
    }
    String? barcode;
    try {
      barcode = await Navigator.of(context).push<String>(
        MaterialPageRoute(builder: (_) => const BarcodeScannerScreen()),
      );
    } catch (error, stackTrace) {
      developer.log(
        'scanner navigation failure',
        name: 'nutritrust.ui',
        error: error,
        stackTrace: stackTrace,
      );
      if (mounted) {
        setState(
          () => _error = 'The barcode scanner could not start. Please retry.',
        );
      }
      return;
    }
    developer.log(
      'scanner returned barcode=${barcode ?? 'none'}',
      name: 'nutritrust.ui',
    );
    if (barcode == null || !mounted || _isLoading) return;
    setState(() {
      _isLoading = true;
      _analysis = null;
      _selectedImage = null;
      _imageBytes = null;
      _error = null;
    });
    try {
      final response = await _api.analyzeBarcode(
        barcode,
        username: widget.username,
      );
      if (!mounted) return;
      setState(() => _analysis = response);
      unawaited(_trackAnalysis(response));
    } on NutriTrustApiException catch (error) {
      developer.log('barcode UI error', name: 'nutritrust.ui', error: error);
      if (mounted) setState(() => _error = error.message);
    } catch (error, stackTrace) {
      developer.log(
        'barcode unexpected UI error',
        name: 'nutritrust.ui',
        error: error,
        stackTrace: stackTrace,
      );
      if (mounted) {
        setState(() => _error = 'The barcode lookup failed. Please retry.');
      }
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  void _openTracker() {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => TrackerScreen(username: widget.username),
      ),
    );
  }

  Map<String, dynamic> _mapValue(Object? value) =>
      value is Map ? Map<String, dynamic>.from(value) : <String, dynamic>{};

  List<String> _textList(Object? value) => value is Iterable
      ? value
          .map((item) => item.toString())
          .where((item) => item.trim().isNotEmpty)
          .toList()
      : <String>[];

  Map<String, double> _nutritionValues(Map<String, dynamic> source) {
    final values = <String, double>{};
    for (final entry in source.entries) {
      final raw = entry.value;
      final value = raw is Map ? raw['value'] : raw;
      if (value is num) values[entry.key] = value.toDouble();
    }
    return values;
  }

  String _localDate(DateTime date) {
    final month = date.month.toString().padLeft(2, '0');
    final day = date.day.toString().padLeft(2, '0');
    return '${date.year}-$month-$day';
  }

  Map<String, dynamic> _trackerPayload(
    Map<String, dynamic> response, {
    String? manualName,
  }) {
    final analysis = _mapValue(response['product_analysis']);
    final product = _mapValue(analysis['product']);
    final nutrition = _mapValue(analysis['nutrition']);
    final serving = _mapValue(nutrition['per_serving']);
    final per100 = _mapValue(nutrition['per_100g']);
    final useServing = serving.isNotEmpty;
    final allergens = _mapValue(analysis['allergens']);
    final classification = _mapValue(analysis['classification']);
    final nutriScore = _mapValue(analysis['nutri_score']);
    final scores = _mapValue(_mapValue(analysis['scoring'])['scores']);
    final grade = nutriScore['grade'] ?? classification['nutriscore_grade'];

    return {
      'username': widget.username,
      'date': _localDate(DateTime.now()),
      'name': manualName ?? product['name'],
      'brand': product['brands'] ?? product['brand'],
      'barcode': product['barcode'] ?? response['barcode'],
      'image_url': product['image_front_url'],
      'source': manualName != null ? 'manual_name' : 'scan',
      'manual_name': manualName != null,
      'nutrition': _nutritionValues(useServing ? serving : per100),
      'nutrition_basis': useServing ? 'per_serving' : 'per_100g',
      'allergens': [
        ..._textList(allergens['declared']),
        ..._textList(allergens['open_food_facts_tags']),
      ],
      'additives': _textList(classification['additives_tags']),
      'nutri_grade': grade,
      'health_score': scores['overall'],
    };
  }

  Future<void> _trackAnalysis(Map<String, dynamic> response) async {
    final product = _mapValue(_mapValue(response['product_analysis'])['product']);
    final scannedName = product['name']?.toString().trim() ?? '';
    String? manualName;
    if (scannedName.isEmpty) {
      if (!mounted) return;
      manualName = await showProductNameDialog(
        context,
        title: 'What did you scan?',
        message:
            'We could not read the product name. Add it so your tracker and '
            'nutrition totals stay clear.',
        allowSkip: true,
      );
    }

    try {
      final result = await _api.addTrackerItem(
        _trackerPayload(response, manualName: manualName),
      );
      if (!mounted) return;
      final item = _mapValue(result['item']);
      final name = item['name']?.toString() ?? manualName ?? 'Item';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('$name added to Tracker'),
          action: SnackBarAction(label: 'View', onPressed: _openTracker),
        ),
      );
    } on NutriTrustApiException catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Scanned, but could not add to Tracker: ${error.message}'),
        ),
      );
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Scanned, but could not add to Tracker.'),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final greeting = widget.username != null
        ? 'Hello, ${widget.username}!'
        : 'Welcome!';

    return Scaffold(
      body: CustomScrollView(
        slivers: [
          SliverAppBar(
            expandedHeight: 160,
            pinned: true,
            backgroundColor: AppTheme.primaryGreen,
            foregroundColor: Colors.white,
            automaticallyImplyLeading: false,
            actions: [
              IconButton(
                tooltip: 'Open tracker',
                icon: Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(
                    Icons.restaurant_menu_rounded,
                    color: Colors.white,
                    size: 20,
                  ),
                ),
                onPressed: _openTracker,
              ),
              const SizedBox(width: 4),
              IconButton(
                tooltip: 'Health profile',
                icon: Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(
                    Icons.tune_rounded,
                    color: Colors.white,
                    size: 20,
                  ),
                ),
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => PersonalHealthInputScreen(
                      initialProfile: widget.profile,
                      username: widget.username,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 8),
            ],
            flexibleSpace: FlexibleSpaceBar(
              background: Container(
                decoration: const BoxDecoration(
                  gradient: AppTheme.primaryGradient,
                ),
                child: SafeArea(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(20, 48, 20, 0),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          greeting,
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w500,
                            color: Colors.white.withValues(alpha: 0.85),
                          ),
                        ),
                        const SizedBox(height: 4),
                        const Text(
                          'Understand what you eat.',
                          style: TextStyle(
                            fontSize: 26,
                            fontWeight: FontWeight.w800,
                            color: Colors.white,
                            letterSpacing: -0.3,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          'Scan a barcode or upload a food label',
                          style: TextStyle(
                            fontSize: 14,
                            color: Colors.white.withValues(alpha: 0.7),
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
                _buildActionCard(
                  icon: Icons.qr_code_scanner_rounded,
                  title: 'Scan Barcode',
                  subtitle: 'Quick product lookup',
                  gradient: const [Color(0xFF1B7A5A), Color(0xFF2EC4B6)],
                  onTap: _isLoading ? null : _scanBarcode,
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: _buildActionCard(
                        icon: Icons.camera_alt_rounded,
                        title: 'Take Photo',
                        subtitle: 'Label analysis',
                        gradient: const [Color(0xFF0D5A3E), Color(0xFF1B7A5A)],
                        onTap: _isLoading
                            ? null
                            : () => _pickImage(ImageSource.camera),
                        compact: true,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: _buildActionCard(
                        icon: Icons.photo_library_rounded,
                        title: 'Gallery',
                        subtitle: 'Choose image',
                        gradient: const [Color(0xFF0D5A3E), Color(0xFF1B7A5A)],
                        onTap: _isLoading
                            ? null
                            : () => _pickImage(ImageSource.gallery),
                        compact: true,
                      ),
                    ),
                  ],
                ),
                if (_imageBytes != null) ...[
                  const SizedBox(height: 20),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(16),
                    child: Image.memory(
                      _imageBytes!,
                      height: 220,
                      fit: BoxFit.contain,
                    ),
                  ),
                  if (_ingredientsBytes != null) ...[
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        const Text(
                          'Ingredients list',
                          style: TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w600,
                            color: AppTheme.textMedium,
                          ),
                        ),
                        const Spacer(),
                        TextButton(
                          onPressed: _isLoading
                              ? null
                              : () => setState(() {
                                  _ingredientsImage = null;
                                  _ingredientsBytes = null;
                                  _analysis = null;
                                }),
                          child: const Text('Remove'),
                        ),
                      ],
                    ),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(16),
                      child: Image.memory(
                        _ingredientsBytes!,
                        height: 140,
                        fit: BoxFit.contain,
                      ),
                    ),
                  ],
                  const SizedBox(height: 8),
                  OutlinedButton.icon(
                    onPressed: _isLoading ? null : _pickIngredients,
                    icon: Icon(
                      _ingredientsBytes == null
                          ? Icons.add_photo_alternate_outlined
                          : Icons.swap_horiz_rounded,
                    ),
                    label: Text(
                      _ingredientsBytes == null
                          ? 'Add ingredients photo (optional)'
                          : 'Replace ingredients photo',
                    ),
                  ),
                  const SizedBox(height: 12),
                  SizedBox(
                    height: 48,
                    child: FilledButton.icon(
                      onPressed: _isLoading ? null : _analyzeImage,
                      icon: const Icon(Icons.document_scanner_outlined),
                      label: const Text('Analyze label'),
                    ),
                  ),
                ],
                if (_isLoading)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 40),
                    child: Column(
                      children: [
                        SizedBox(
                          width: 48,
                          height: 48,
                          child: CircularProgressIndicator(
                            strokeWidth: 3,
                            color: AppTheme.primaryGreen,
                            backgroundColor: AppTheme.primaryGreen.withValues(
                              alpha: 0.15,
                            ),
                          ),
                        ),
                        const SizedBox(height: 16),
                        const Text(
                          'Analyzing…',
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w500,
                            color: AppTheme.textMedium,
                          ),
                        ),
                        const SizedBox(height: 4),
                        const Text(
                          'This may take a moment',
                          style: TextStyle(
                            fontSize: 13,
                            color: AppTheme.textLight,
                          ),
                        ),
                      ],
                    ),
                  ),
                if (_error != null) ...[
                  const SizedBox(height: 20),
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: Colors.red.shade50,
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: Colors.red.shade200),
                    ),
                    child: Row(
                      children: [
                        Icon(
                          Icons.error_outline,
                          color: Colors.red.shade700,
                          size: 22,
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            _error!,
                            style: TextStyle(
                              color: Colors.red.shade900,
                              fontSize: 14,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 8),
                  TextButton.icon(
                    onPressed: _imageBytes == null
                        ? _scanBarcode
                        : _analyzeImage,
                    icon: const Icon(Icons.refresh_rounded),
                    label: const Text('Retry'),
                  ),
                ],
                if (_analysis != null) ...[
                  const SizedBox(height: 24),
                  NutritionReport(
                    response: _analysis!,
                    api: _api,
                    profile: widget.profile,
                    username: widget.username,
                  ),
                ],
                const SizedBox(height: 40),
              ]),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildActionCard({
    required IconData icon,
    required String title,
    required String subtitle,
    required List<Color> gradient,
    VoidCallback? onTap,
    bool compact = false,
  }) {
    return Material(
      borderRadius: BorderRadius.circular(18),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Ink(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: gradient,
            ),
          ),
          padding: EdgeInsets.all(compact ? 16 : 20),
          child: Row(
            children: [
              Container(
                padding: EdgeInsets.all(compact ? 10 : 12),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.18),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Icon(icon, color: Colors.white, size: compact ? 24 : 28),
              ),
              SizedBox(width: compact ? 12 : 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: TextStyle(
                        fontSize: compact ? 15 : 17,
                        fontWeight: FontWeight.w700,
                        color: Colors.white,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      subtitle,
                      style: TextStyle(
                        fontSize: compact ? 12 : 13,
                        color: Colors.white.withValues(alpha: 0.7),
                      ),
                    ),
                  ],
                ),
              ),
              Icon(
                Icons.arrow_forward_ios_rounded,
                color: Colors.white.withValues(alpha: 0.5),
                size: 18,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// NutritionReport
// ---------------------------------------------------------------------------

class NutritionReport extends StatelessWidget {
  const NutritionReport({
    super.key,
    required this.response,
    required this.api,
    this.profile,
    this.username,
  });

  final Map<String, dynamic> response;
  final NutriTrustApiService api;
  final HealthProfile? profile;
  final String? username;

  Map<String, dynamic> _map(Object? v) =>
      v is Map ? Map<String, dynamic>.from(v) : <String, dynamic>{};
  List<Object?> _list(Object? v) => v is List ? v : <Object?>[];
  String _text(Object? v) =>
      v == null || v.toString().trim().isEmpty ? 'Not available' : v.toString();
  String _number(Object? v) =>
      v is num ? (v % 1 == 0 ? v.toInt().toString() : v.toString()) : _text(v);

  String _nutrient(Object? value) {
    final item = _map(value);
    if (item.isEmpty || item['value'] is! num || item['unit'] == null) {
      return '';
    }
    final q = item['status'] == 'approximate' ? '~' : '';
    return '$q${_number(item['value'])} ${_text(item['unit'])}';
  }

  @override
  Widget build(BuildContext context) {
    final analysis = _map(response['product_analysis']);
    final product = _map(analysis['product']);
    final nutrition = _map(analysis['nutrition']);
    final serving = _map(nutrition['per_serving']);
    final per100 = _map(nutrition['per_100g']);
    final norm = _map(response['normalized_nutrition']);
    final normServing = _map(norm['serving_size']);
    final label = _map(response['food_label']);
    final dv = _map(label['daily_values_percent']);
    final ingredients = _map(analysis['ingredients']);
    final allergens = _map(analysis['allergens']);
    final classification = _map(analysis['classification']);
    final nutriEngine = _map(
      analysis['nutri_score'] ?? response['nutri_score'],
    );
    final novaEngine = _map(analysis['nova'] ?? response['nova']);
    final additiveEngine = _map(
      analysis['additive_regulatory'] ?? response['additive_regulatory'],
    );
    final scoring = _map(analysis['scoring'] ?? response['scoring']);
    final warnings = _visibleWarnings(_list(analysis['warnings']));
    final requestedBarcode = _map(
      analysis['identification'],
    )['requested_barcode'];
    final hasAssessmentData =
        scoring.isNotEmpty ||
        nutriEngine.isNotEmpty ||
        novaEngine.isNotEmpty ||
        additiveEngine.isNotEmpty;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildProductHeader(
          context,
          product,
          requestedBarcode,
          normServing,
          analysis,
        ),
        const SizedBox(height: 16),
        AiSummaryCard(api: api, response: response, username: username),
        const SizedBox(height: 16),
        if (profile?.hasInformation == true) ...[
          PersonalizedInsights(profile: profile!, analysis: analysis),
          const SizedBox(height: 16),
        ],
        if (hasAssessmentData)
          _buildScoreOverview(context, scoring, classification, nutriEngine),
        _buildNutrientSection(context, 'Energy', Icons.bolt_rounded, [
          _nutrientBar(
            'Calories',
            serving['energy_kcal'],
            per100['energy_kcal'],
            dv['energy_kcal'],
            false,
          ),
        ]),
        _buildNutrientSection(
          context,
          'Macronutrients',
          Icons.restaurant_rounded,
          [
            _nutrientBar(
              'Total fat',
              serving['total_fat'],
              per100['total_fat'],
              dv['total_fat'],
              true,
            ),
            _nutrientBar(
              'Saturated fat',
              serving['saturated_fat'],
              per100['saturated_fat'],
              dv['saturated_fat'],
              true,
            ),
            _nutrientBar(
              'Trans fat',
              serving['trans_fat'],
              per100['trans_fat'],
              dv['trans_fat'],
              true,
            ),
            _nutrientBar(
              'Carbohydrates',
              serving['total_carbohydrate'],
              per100['total_carbohydrate'],
              dv['total_carbohydrate'],
              false,
            ),
            _nutrientBar(
              'Fiber',
              serving['fiber'],
              per100['fiber'],
              dv['dietary_fiber'],
              false,
            ),
            _nutrientBar(
              'Total sugars',
              serving['sugar'],
              per100['sugar'],
              dv['total_sugars'],
              true,
            ),
            _nutrientBar(
              'Added sugars',
              serving['added_sugar'],
              per100['added_sugar'],
              dv['added_sugars'],
              true,
            ),
            _nutrientBar(
              'Protein',
              serving['protein'],
              per100['protein'],
              dv['protein'],
              false,
            ),
          ],
        ),
        _buildNutrientSection(
          context,
          'Other Nutrients',
          Icons.science_rounded,
          [
            _nutrientBar(
              'Sodium',
              serving['sodium'],
              per100['sodium'],
              dv['sodium'],
              true,
            ),
            _nutrientBar(
              'Cholesterol',
              serving['cholesterol'],
              per100['cholesterol'],
              dv['cholesterol'],
              true,
            ),
            _nutrientBar(
              'Calcium',
              serving['calcium'],
              per100['calcium'],
              dv['calcium'],
              false,
            ),
            _nutrientBar(
              'Iron',
              serving['iron'],
              per100['iron'],
              dv['iron'],
              false,
            ),
            _nutrientBar(
              'Potassium',
              serving['potassium'],
              per100['potassium'],
              dv['potassium'],
              false,
            ),
          ],
        ),
        if (hasAssessmentData)
          _buildAssessments(
            context,
            scoring,
            classification,
            nutriEngine,
            novaEngine,
            additiveEngine,
          ),
        _buildIngredientsCard(context, ingredients, allergens),
        if (warnings.isNotEmpty) _buildWarningsCard(context, warnings),
      ],
    );
  }

  // --- Product header ---
  Widget _buildProductHeader(
    BuildContext context,
    Map<String, dynamic> product,
    Object? requestedBarcode,
    Map<String, dynamic> normServing,
    Map<String, dynamic> analysis,
  ) {
    final imageUrl = product['image_front_url']?.toString();
    final hasImage = imageUrl != null && imageUrl.isNotEmpty;

    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.06),
            blurRadius: 16,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (hasImage)
            Container(
              width: double.infinity,
              height: 200,
              color: Colors.grey.shade100,
              child: Image.network(
                imageUrl,
                fit: BoxFit.contain,
                errorBuilder: (_, _, _) => Center(
                  child: Icon(
                    Icons.image_not_supported_outlined,
                    size: 48,
                    color: Colors.grey.shade400,
                  ),
                ),
              ),
            ),
          Padding(
            padding: const EdgeInsets.all(18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _text(product['name']),
                  style: const TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.w700,
                    color: AppTheme.textDark,
                    letterSpacing: -0.2,
                  ),
                ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 6,
                  children: [
                    if (_text(product['brands']) != 'Not available')
                      _infoPill(
                        Icons.storefront_outlined,
                        product['brands'].toString(),
                      ),
                    if (_text(product['barcode'] ?? requestedBarcode) !=
                        'Not available')
                      _infoPill(
                        Icons.qr_code,
                        (product['barcode'] ?? requestedBarcode).toString(),
                      ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _infoPill(IconData icon, String text) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: Colors.grey.shade100,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: AppTheme.textMedium),
          const SizedBox(width: 4),
          Flexible(
            child: Text(
              text,
              style: const TextStyle(fontSize: 12, color: AppTheme.textMedium),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }

  // --- Score overview ---
  Widget _buildScoreOverview(
    BuildContext context,
    Map<String, dynamic> scoring,
    Map<String, dynamic> classification,
    Map<String, dynamic> nutriEngine,
  ) {
    final scores = _map(scoring['scores']);
    final overall = scores['overall'];
    final grade = _text(scores['grade']);
    final gradeLabel = _text(scores['grade_label']);
    final engineGrade = nutriEngine['grade']?.toString();
    final nutriScore = (engineGrade != null && engineGrade.isNotEmpty)
        ? engineGrade
        : classification['nutriscore_grade']?.toString();

    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.05),
            blurRadius: 12,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (overall is num)
                ScoreRing(
                  score: overall,
                  size: 110,
                  strokeWidth: 10,
                  grade: grade != 'Not available' ? grade : null,
                  label: 'NutriTrust',
                )
              else
                Container(
                  width: 110,
                  height: 110,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    border: Border.all(color: Colors.grey.shade300, width: 2),
                  ),
                  child: const Text(
                    'N/A',
                    style: TextStyle(
                      fontSize: 22,
                      fontWeight: FontWeight.w600,
                      color: AppTheme.textLight,
                    ),
                  ),
                ),
              const SizedBox(width: 20),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const SizedBox(height: 8),
                    if (grade != 'Not available')
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 12,
                          vertical: 4,
                        ),
                        decoration: BoxDecoration(
                          color: AppTheme.gradeColor(
                            grade,
                          ).withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          gradeLabel != 'Not available' ? gradeLabel : grade,
                          style: TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w700,
                            color: AppTheme.gradeColor(grade),
                          ),
                        ),
                      ),
                    const SizedBox(height: 10),
                    if (nutriScore != null) _buildNutriScoreVisual(nutriScore),
                    if (nutriEngine.isNotEmpty) ...[
                      const SizedBox(height: 6),
                      Text(
                        _nutriScoreStatus(nutriEngine),
                        style: const TextStyle(
                          fontSize: 12,
                          color: AppTheme.textMedium,
                        ),
                      ),
                    ],
                    const SizedBox(height: 10),
                    Text(
                      'Why this rating',
                      style: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w700,
                        color: AppTheme.textMedium,
                      ),
                    ),
                    const SizedBox(height: 4),
                    ..._ratingReasons(scoring).map(
                      (reason) => Padding(
                        padding: const EdgeInsets.only(bottom: 3),
                        child: Text(
                          '• $reason',
                          style: const TextStyle(
                            fontSize: 12,
                            height: 1.35,
                            color: AppTheme.textLight,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildNutriScoreVisual(String grade) {
    const labels = ['A', 'B', 'C', 'D', 'E'];
    final active = grade.toUpperCase();

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: labels.map((l) {
        final isActive = l == active;
        final color =
            AppTheme.nutriScoreColors[l.toLowerCase()] ?? AppTheme.textLight;
        return Container(
          margin: const EdgeInsets.only(right: 3),
          width: isActive ? 30 : 24,
          height: isActive ? 30 : 24,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: isActive ? color : color.withValues(alpha: 0.15),
            borderRadius: BorderRadius.circular(6),
            boxShadow: isActive
                ? [
                    BoxShadow(
                      color: color.withValues(alpha: 0.4),
                      blurRadius: 6,
                    ),
                  ]
                : null,
          ),
          child: Text(
            l,
            style: TextStyle(
              fontSize: isActive ? 15 : 12,
              fontWeight: FontWeight.w800,
              color: isActive ? Colors.white : color,
            ),
          ),
        );
      }).toList(),
    );
  }

  String _nutriScoreStatus(Map<String, dynamic> engine) {
    if (engine['status'] == 'engine_error') {
      return _text(engine['warning']);
    }
    if (engine['grade'] != null) {
      return 'Calculated grade ${engine['grade']}; score ${_number(engine['score'])}'
          ' (${_text(engine['status'])})';
    }
    final missing = _list(engine['missing_inputs']);
    if (missing.isNotEmpty) {
      return 'Not calculated: missing ${missing.join(', ')}.';
    }
    final warnings = _list(engine['warnings'])
        .map((w) => w?.toString().trim() ?? '')
        .where((w) => w.isNotEmpty)
        .toList();
    if (warnings.isNotEmpty) return 'Not calculated: ${warnings.first}';
    return _text(engine['status']);
  }

  String _additiveDetails(
    Map<String, dynamic> engine,
    Map<String, dynamic> legacy,
  ) {
    if (engine.isEmpty) return _text(legacy['details']);
    if (engine['status'] == 'engine_error') return _text(engine['warning']);
    final warnings = _list(engine['warnings'])
        .map((w) => w?.toString().trim() ?? '')
        .where((w) => w.isNotEmpty)
        .toList();
    if (warnings.isNotEmpty) return warnings.first;
    return _text(engine['important_notice']);
  }

  String _additiveLine(Map<String, dynamic> item) {
    final code = _text(item['identified_as']);
    final name = item['name']?.toString().trim() ?? '';
    final title = name.isEmpty ? 'Name not listed ($code)' : '$name ($code)';
    final permission = _additivePermissionLabel(item['permission_status']);
    final compliance = item['compliance_status']?.toString();
    final functions = _list(item['functional_class'])
        .map((value) => value?.toString().trim() ?? '')
        .where((value) => value.isNotEmpty)
        .join(', ');
    final notes = _list(item['notes'])
        .map((value) => value?.toString().trim() ?? '')
        .where((value) => value.isNotEmpty)
        .toList();
    final purpose = item['purpose']?.toString().trim() ?? '';
    final referenceRisk = item['reference_risk']?.toString().trim() ?? '';
    final maxLevel = _map(item['max_level']);
    final lines = <String>[title];
    for (final note in notes) {
      lines.add('Note: $note');
    }
    lines.add(
      'Function class: ${functions.isEmpty ? 'Not listed in local additive data' : functions}',
    );
    if (purpose.isNotEmpty) {
      lines.add(
        functions.isEmpty
            ? 'Purpose / note: $purpose'
            : 'Reference note: $purpose',
      );
    }
    if (referenceRisk.isNotEmpty) {
      lines.add('Legacy reference-list rating: $referenceRisk');
    }

    final ins = _list(item['ins'])
        .map((value) => value?.toString().trim() ?? '')
        .where((value) => value.isNotEmpty)
        .join(', ');
    if (ins.isNotEmpty) lines.add('INS: $ins');

    const verifiedPermissionStatuses = {
      'permitted_gmp',
      'permitted_with_conditions',
      'restricted_or_not_permitted',
    };
    if (verifiedPermissionStatuses.contains(item['permission_status'])) {
      lines.add('Legal status: $permission');
    }
    if (compliance == 'compliant') {
      lines.add('Label amount check: within the recorded limit');
    } else if (compliance == 'non_compliant') {
      lines.add('Label amount check: exceeds the recorded limit');
    }

    final applicableRule = item['applicable_rule']?.toString().trim() ?? '';
    if (applicableRule.isNotEmpty) {
      lines.add('Applicable rule: $applicableRule');
    }
    if (maxLevel.isNotEmpty) {
      lines.add(
        'Maximum level: ${_number(maxLevel['value'])} ${_text(maxLevel['unit'])} '
        '(${_text(maxLevel['basis'])})',
      );
    }
    final conditions = _list(item['conditions'])
        .map((value) => value?.toString().trim() ?? '')
        .where((value) => value.isNotEmpty)
        .toList();
    if (conditions.isNotEmpty) {
      lines.add('Conditions: ${conditions.join('; ')}');
    }

    for (final rawNote in _list(item['regulatory_notes'])) {
      if (rawNote is! Map) continue;
      final note = Map<String, dynamic>.from(rawNote);
      final details = <String>[];
      final category = note['category'] ?? note['fcs'];
      if (category != null && category.toString().trim().isNotEmpty) {
        details.add('Food category: $category');
      }
      final recordedMaximum = note['max_level'];
      if (recordedMaximum != null) {
        details.add('Recorded maximum: $recordedMaximum');
      }
      final noteText = note['note']?.toString().trim() ?? '';
      if (noteText.isNotEmpty) details.add(noteText);
      final ruleConditions = _list(note['conditions'])
          .map((value) => value?.toString().trim() ?? '')
          .where((value) => value.isNotEmpty)
          .toList();
      if (ruleConditions.isNotEmpty) {
        details.add('Conditions: ${ruleConditions.join('; ')}');
      }
      final ruleReference = _map(note['reference']);
      final referenceId = ruleReference['id']?.toString().trim() ?? '';
      final referenceSection =
          ruleReference['section']?.toString().trim() ?? '';
      if (referenceId.isNotEmpty) {
        details.add(
          'Reference: $referenceId${referenceSection.isEmpty ? '' : ', $referenceSection'}',
        );
      }
      if (details.isNotEmpty) {
        lines.add('Regulatory reference note: ${details.join('; ')}');
      }
    }

    final reference = _map(item['reference']);
    final document = reference['document']?.toString().trim() ?? '';
    final section = reference['section']?.toString().trim() ?? '';
    if (document.isNotEmpty) {
      lines.add(
        'Regulatory source: $document${section.isEmpty ? '' : ', $section'}',
      );
    }
    for (final limitation in _list(item['limitations'])) {
      final text = limitation?.toString().trim() ?? '';
      if (text.isNotEmpty && !notes.contains(text)) {
        lines.add('Assessment note: $text');
      }
    }
    return lines.join('\n');
  }

  String _additivePermissionLabel(Object? status) {
    switch (status?.toString()) {
      case 'permitted_gmp':
        return 'permitted under GMP';
      case 'permitted_with_conditions':
        return 'permitted with category conditions';
      case 'restricted_or_not_permitted':
        return 'restricted or not permitted';
      case 'unable_to_verify':
        return '';
      default:
        return _text(status);
    }
  }

  List<String> _ratingReasons(Map<String, dynamic> scoring) {
    final reasons = _list(scoring['rating_reasons'])
        .map((value) => value?.toString().trim() ?? '')
        .where((value) => value.isNotEmpty)
        .take(2)
        .toList();
    if (reasons.isNotEmpty) return reasons;
    final explanation = scoring['explanation']?.toString().trim() ?? '';
    return explanation.isEmpty
        ? ['Based on the available product information.']
        : [explanation];
  }

  List<Object?> _visibleWarnings(List<Object?> warnings) {
    const importantSignals = [
      'could not be completed',
      'identity conflicts',
      'could not be reached',
      'timed out',
      'no readable text',
      'not permitted',
      'non-compliant',
    ];
    final visible = <Object?>[];
    for (final warning in warnings) {
      final text = warning?.toString().trim() ?? '';
      if (text.isEmpty || !importantSignals.any(text.toLowerCase().contains))
        continue;
      if (!visible.any((item) => item.toString() == text)) visible.add(text);
      if (visible.length == 2) break;
    }
    return visible;
  }

  // --- Nutrient section ---
  Widget _buildNutrientSection(
    BuildContext context,
    String title,
    IconData icon,
    List<Widget> children,
  ) {
    final visible = children.whereType<NutrientBar>().where((c) {
      return c.servingValue.isNotEmpty || c.per100Value.isNotEmpty;
    }).toList();

    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.05),
            blurRadius: 12,
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
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: AppTheme.primaryGreen.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(icon, color: AppTheme.primaryGreen, size: 18),
              ),
              const SizedBox(width: 10),
              Text(
                title,
                style: const TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w700,
                  color: AppTheme.textDark,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          if (visible.isNotEmpty)
            ...visible
          else
            // Keep the section visible when nothing was found for it, so a
            // barcode with incomplete data still shows every part of the
            // report instead of silently dropping it.
            Row(
              children: [
                Icon(
                  Icons.help_outline_rounded,
                  size: 16,
                  color: Colors.grey.shade400,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'Not available in the data found for this product.',
                    style: TextStyle(fontSize: 13, color: Colors.grey.shade600),
                  ),
                ),
              ],
            ),
        ],
      ),
    );
  }

  Widget _nutrientBar(
    String name,
    Object? servingRaw,
    Object? per100Raw,
    Object? dvPercent,
    bool isLimit,
  ) {
    return NutrientBar(
      label: name,
      servingValue: _nutrient(servingRaw),
      per100Value: _nutrient(per100Raw),
      dvPercent: dvPercent is num ? dvPercent : null,
      isLimitNutrient: isLimit,
    );
  }

  // --- Assessment sections (barcode results) ---
  Widget _buildAssessments(
    BuildContext context,
    Map<String, dynamic> scoring,
    Map<String, dynamic> classification,
    Map<String, dynamic> nutriEngine,
    Map<String, dynamic> novaEngine,
    Map<String, dynamic> additiveEngine,
  ) {
    final scores = _map(scoring['scores']);
    final limits = _map(scores['nutrient_limits']);
    final nova = _map(scores['nova_processing']);
    final additives = _map(scores['additive_safety']);
    final trafficLights = _map(limits['traffic_lights']);
    final engineNutriGrade = nutriEngine['grade']?.toString();
    final nutriGrade =
        engineNutriGrade ?? classification['nutriscore_grade']?.toString();
    final engineNovaGroup = novaEngine['group'] is num
        ? (novaEngine['group'] as num).toInt()
        : null;
    final legacyNovaGroup = nova['nova_group'] is num
        ? (nova['nova_group'] as num).toInt()
        : null;
    final novaGroup = engineNovaGroup ?? legacyNovaGroup;
    final additiveItems = _list(
      additiveEngine['additives'],
    ).whereType<Map>().toList();
    final additiveStatusLabel = _additiveStatusLabel(
      additiveEngine['overall_status'] ?? additives['status'],
    );

    return Column(
      children: [
        // Nutri-Score card
        _assessmentCard(
          context,
          icon: Icons.grade_rounded,
          title: 'Nutri-Score',
          color: AppTheme.gradeColor(nutriGrade ?? ''),
          children: [
            if (nutriGrade != null) ...[
              _buildNutriScoreVisual(nutriGrade),
              const SizedBox(height: 8),
            ],
            Text(
              engineNutriGrade != null
                  ? 'Calculated: $engineNutriGrade'
                  : nutriGrade == null
                  ? 'Not available'
                  : 'Reported: $nutriGrade',
              style: const TextStyle(fontSize: 13, color: AppTheme.textMedium),
            ),
          ],
        ),
        // Traffic lights
        _assessmentCard(
          context,
          icon: Icons.traffic_rounded,
          title: 'UK Traffic Lights',
          color: AppTheme.accentAmber,
          children: [
            ...['total_fat', 'saturated_fat', 'sugar', 'salt'].map((key) {
              final item = _map(trafficLights[key]);
              if (item.isEmpty) return const SizedBox.shrink();
              final color = AppTheme.trafficLightColor(
                item['color']?.toString(),
              );
              return Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Row(
                  children: [
                    Container(
                      width: 14,
                      height: 14,
                      decoration: BoxDecoration(
                        color: color,
                        shape: BoxShape.circle,
                        boxShadow: [
                          BoxShadow(
                            color: color.withValues(alpha: 0.4),
                            blurRadius: 4,
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        '${key.replaceAll('_', ' ').toUpperCase()}: '
                        '${item['value'] == null ? 'unavailable' : '${_number(item['value'])} ${item['unit']}'}',
                        style: const TextStyle(
                          fontSize: 13,
                          color: AppTheme.textMedium,
                        ),
                      ),
                    ),
                  ],
                ),
              );
            }),
          ],
        ),
        // NOVA
        _assessmentCard(
          context,
          icon: Icons.science_outlined,
          title: 'NOVA Classification',
          color: const Color(0xFF7B1FA2),
          children: [
            if (novaGroup != null) ...[
              _buildNovaVisual(novaGroup),
              const SizedBox(height: 8),
            ],
            Text(
              novaGroup == null ? 'Not available' : 'Group $novaGroup',
              style: const TextStyle(fontSize: 13, color: AppTheme.textMedium),
            ),
          ],
        ),
        // Additives
        _assessmentCard(
          context,
          icon: Icons.biotech_outlined,
          title: 'Additive Safety',
          color: const Color(0xFF00897B),
          children: [
            if (additiveStatusLabel.isNotEmpty)
              Text(
                additiveStatusLabel,
                style: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                  color: AppTheme.textMedium,
                ),
              ),
            const SizedBox(height: 6),
            if (additiveItems.isNotEmpty)
              ...additiveItems.map(
                (item) => Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: AdditiveCard(
                    code: item['identified_as']?.toString() ?? '',
                    name: item['name']?.toString().trim() ?? '',
                    note: (() { final n = item['notes'] as List?; return (n != null && n.isNotEmpty) ? n.first.toString().trim() : ''; })(),
                  ),
                ),
              )
            else
              Text(
                _additiveDetails(additiveEngine, additives),
                style: const TextStyle(
                  fontSize: 12,
                  color: AppTheme.textMedium,
                ),
              ),
          ],
        ),
      ],
    );
  }

  String _additiveStatusLabel(Object? status) {
    switch (status?.toString()) {
      case 'permitted_gmp':
        return 'Permitted under good manufacturing practice';
      case 'permitted_with_conditions':
        return 'Permitted with category conditions';
      case 'restricted_or_not_permitted':
        return 'Restricted or not permitted';
      case 'no_additives_identified':
        return 'No additives identified';
      case 'insufficient_information':
        return '';
      case 'known':
        return 'Additive assessment complete';
      default:
        return 'Additive status: ${_text(status)}';
    }
  }

  Widget _buildNovaVisual(int group) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: List.generate(4, (i) {
        final g = i + 1;
        final isActive = g == group;
        const novaColors = [
          Color(0xFF4CAF50),
          Color(0xFFFF9800),
          Color(0xFFFF5722),
          Color(0xFFD32F2F),
        ];
        final color = novaColors[i];
        return Container(
          margin: const EdgeInsets.only(right: 4),
          width: isActive ? 36 : 28,
          height: isActive ? 36 : 28,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: isActive ? color : color.withValues(alpha: 0.12),
            borderRadius: BorderRadius.circular(8),
            boxShadow: isActive
                ? [
                    BoxShadow(
                      color: color.withValues(alpha: 0.4),
                      blurRadius: 6,
                    ),
                  ]
                : null,
          ),
          child: Text(
            '$g',
            style: TextStyle(
              fontSize: isActive ? 16 : 13,
              fontWeight: FontWeight.w800,
              color: isActive ? Colors.white : color,
            ),
          ),
        );
      }),
    );
  }

  Widget _assessmentCard(
    BuildContext context, {
    required IconData icon,
    required String title,
    required Color color,
    required List<Widget> children,
  }) {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.05),
            blurRadius: 12,
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
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(icon, color: color, size: 18),
              ),
              const SizedBox(width: 10),
              Text(
                title,
                style: const TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w700,
                  color: AppTheme.textDark,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          ...children,
        ],
      ),
    );
  }

  // --- Ingredients card ---
  Widget _buildIngredientsCard(
    BuildContext context,
    Map<String, dynamic> ingredients,
    Map<String, dynamic> allergens,
  ) {
    return _assessmentCard(
      context,
      icon: Icons.list_alt_rounded,
      title: 'Ingredients & Allergens',
      color: const Color(0xFF5D4037),
      children: [
        if (_text(ingredients['text']) != 'Not available') ...[
          Text(
            'Ingredients',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w600,
              color: Colors.grey.shade600,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            ingredients['text'].toString(),
            style: const TextStyle(
              fontSize: 13,
              height: 1.4,
              color: AppTheme.textMedium,
            ),
          ),
          const SizedBox(height: 12),
        ],
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(
              _list(allergens['declared']).isEmpty
                  ? Icons.check_circle_outline
                  : Icons.warning_amber_rounded,
              size: 16,
              color: _list(allergens['declared']).isEmpty
                  ? const Color(0xFF2E7D32)
                  : const Color(0xFFE65100),
            ),
            const SizedBox(width: 6),
            Expanded(
              child: Text(
                'Declared allergens: ${_list(allergens['declared']).isEmpty ? 'Unknown — no declaration was identified' : _list(allergens['declared']).join(', ')}',
                style: const TextStyle(
                  fontSize: 13,
                  color: AppTheme.textMedium,
                ),
              ),
            ),
          ],
        ),
        if (_text(_map(allergens['precautionary_traces'])['text']) !=
            'Not available')
          Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(
                  Icons.info_outline,
                  size: 14,
                  color: AppTheme.textLight,
                ),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    'May contain: ${_map(allergens['precautionary_traces'])['text']}',
                    style: const TextStyle(
                      fontSize: 12,
                      color: AppTheme.textLight,
                    ),
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }

  // --- Warnings card ---
  Widget _buildWarningsCard(BuildContext context, List<Object?> warnings) {
    return _assessmentCard(
      context,
      icon: Icons.report_outlined,
      title: 'Warnings',
      color: const Color(0xFFE65100),
      children: warnings
          .map(
            (w) => Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('• ', style: TextStyle(color: Color(0xFFE65100))),
                  Expanded(
                    child: Text(
                      _text(w),
                      style: const TextStyle(
                        fontSize: 13,
                        color: AppTheme.textMedium,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          )
          .toList(),
    );
  }
}
