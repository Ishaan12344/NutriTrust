import 'dart:developer' as developer;
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../models/health_profile.dart';
import '../services/nutritrust_api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/nutrient_bar.dart';
import '../widgets/personalized_insights.dart';
import '../widgets/score_ring.dart';
import 'barcode_scanner_screen.dart';
import 'personal_health_input_screen.dart';

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
  Map<String, dynamic>? _analysis;
  bool _isLoading = false;
  String? _error;

  @override
  void dispose() {
    _api.close();
    super.dispose();
  }

  Future<void> _pickImage(ImageSource source) async {
    try {
      final image = await _picker.pickImage(source: source, imageQuality: 90);
      developer.log('image picker returned: ${image?.name ?? 'cancelled'}',
          name: 'nutritrust.ui');
      if (image == null || !mounted) return;

      final bytes = await image.readAsBytes();
      developer.log(
          'image selected: name=${image.name} size=${bytes.length} type=${image.mimeType ?? 'unknown'}',
          name: 'nutritrust.ui');
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
        _selectedImage = image;
        _imageBytes = bytes;
        _analysis = null;
        _error = null;
      });
      await _analyzeImage();
    } catch (e, stackTrace) {
      developer.log('image pick error',
          name: 'nutritrust.ui', error: e, stackTrace: stackTrace);
      if (mounted) setState(() => _error = 'Unable to select that image.');
    }
  }

  Future<void> _analyzeImage() async {
    final image = _selectedImage;
    final bytes = _imageBytes;
    if (image == null || bytes == null || _isLoading) return;
    developer.log('label callback triggered; api=${_api.baseUrl}',
        name: 'nutritrust.ui');
    setState(() {
      _isLoading = true;
      _error = null;
    });
    try {
      final name = image.name;
      final response = await _api.analyzeLabel(
        imageBytes: bytes,
        filename: name,
        contentType:
            name.toLowerCase().endsWith('.png') ? 'image/png' : 'image/jpeg',
        username: widget.username,
      );
      if (mounted) setState(() => _analysis = response);
    } on NutriTrustApiException catch (error) {
      developer.log('label UI error', name: 'nutritrust.ui', error: error);
      if (mounted) setState(() => _error = error.message);
    } catch (error, stackTrace) {
      developer.log('label unexpected UI error',
          name: 'nutritrust.ui', error: error, stackTrace: stackTrace);
      if (mounted) {
        setState(
            () => _error = 'The label could not be analyzed. Please retry.');
      }
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  Future<void> _scanBarcode() async {
    developer.log('barcode button triggered; api=${_api.baseUrl}',
        name: 'nutritrust.ui');
    if (mounted) {
      setState(() {
        _selectedImage = null;
        _imageBytes = null;
        _error = null;
      });
    }
    String? barcode;
    try {
      barcode = await Navigator.of(context).push<String>(
          MaterialPageRoute(builder: (_) => const BarcodeScannerScreen()));
    } catch (error, stackTrace) {
      developer.log('scanner navigation failure',
          name: 'nutritrust.ui', error: error, stackTrace: stackTrace);
      if (mounted) {
        setState(() =>
            _error = 'The barcode scanner could not start. Please retry.');
      }
      return;
    }
    developer.log('scanner returned barcode=${barcode ?? 'none'}',
        name: 'nutritrust.ui');
    if (barcode == null || !mounted || _isLoading) return;
    setState(() {
      _isLoading = true;
      _analysis = null;
      _selectedImage = null;
      _imageBytes = null;
      _error = null;
    });
    try {
      final response =
          await _api.analyzeBarcode(barcode, username: widget.username);
      if (mounted) setState(() => _analysis = response);
    } on NutriTrustApiException catch (error) {
      developer.log('barcode UI error', name: 'nutritrust.ui', error: error);
      if (mounted) setState(() => _error = error.message);
    } catch (error, stackTrace) {
      developer.log('barcode unexpected UI error',
          name: 'nutritrust.ui', error: error, stackTrace: stackTrace);
      if (mounted) {
        setState(() => _error = 'The barcode lookup failed. Please retry.');
      }
    } finally {
      if (mounted) setState(() => _isLoading = false);
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
                icon: Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.15),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(Icons.tune_rounded,
                      color: Colors.white, size: 20),
                ),
                onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                    builder: (_) => PersonalHealthInputScreen(
                        initialProfile: widget.profile,
                        username: widget.username))),
              ),
              const SizedBox(width: 8),
            ],
            flexibleSpace: FlexibleSpaceBar(
              background: Container(
                decoration: const BoxDecoration(gradient: AppTheme.primaryGradient),
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
                            color: Colors.white.withOpacity(0.85),
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
                            color: Colors.white.withOpacity(0.7),
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
                    child: Image.memory(_imageBytes!,
                        height: 220, fit: BoxFit.contain),
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
                            backgroundColor: AppTheme.primaryGreen.withOpacity(0.15),
                          ),
                        ),
                        const SizedBox(height: 16),
                        const Text('Analyzing…',
                            style: TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.w500,
                                color: AppTheme.textMedium)),
                        const SizedBox(height: 4),
                        const Text('This may take a moment',
                            style: TextStyle(
                                fontSize: 13, color: AppTheme.textLight)),
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
                        Icon(Icons.error_outline,
                            color: Colors.red.shade700, size: 22),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(_error!,
                              style: TextStyle(
                                  color: Colors.red.shade900, fontSize: 14)),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 8),
                  TextButton.icon(
                    onPressed:
                        _imageBytes == null ? _scanBarcode : _analyzeImage,
                    icon: const Icon(Icons.refresh_rounded),
                    label: const Text('Retry'),
                  ),
                ],
                if (_analysis != null) ...[
                  const SizedBox(height: 24),
                  NutritionReport(
                      response: _analysis!, profile: widget.profile),
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
                  color: Colors.white.withOpacity(0.18),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Icon(icon,
                    color: Colors.white, size: compact ? 24 : 28),
              ),
              SizedBox(width: compact ? 12 : 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title,
                        style: TextStyle(
                          fontSize: compact ? 15 : 17,
                          fontWeight: FontWeight.w700,
                          color: Colors.white,
                        )),
                    const SizedBox(height: 2),
                    Text(subtitle,
                        style: TextStyle(
                          fontSize: compact ? 12 : 13,
                          color: Colors.white.withOpacity(0.7),
                        )),
                  ],
                ),
              ),
              Icon(Icons.arrow_forward_ios_rounded,
                  color: Colors.white.withOpacity(0.5), size: 18),
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
  const NutritionReport({super.key, required this.response, this.profile});

  final Map<String, dynamic> response;
  final HealthProfile? profile;

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
    final health = _map(analysis['health_analysis']);
    final scoring = _map(analysis['scoring'] ?? response['scoring']);
    final findings = _list(health['findings']).whereType<Map>();
    final warnings = [
      ..._list(analysis['warnings']),
      ..._list(analysis['missing_data_warnings'])
    ];
    final requestedBarcode = _map(analysis['identification'])['requested_barcode'];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildProductHeader(context, product, requestedBarcode, normServing, analysis),
        const SizedBox(height: 16),
        if (profile?.hasInformation == true) ...[
          PersonalizedInsights(profile: profile!, analysis: analysis),
          const SizedBox(height: 16),
        ],
        if (scoring.isNotEmpty)
          _buildScoreOverview(context, scoring, classification),
        _buildNutrientSection(context, 'Energy', Icons.bolt_rounded, [
          _nutrientBar('Calories', serving['energy_kcal'], per100['energy_kcal'],
              dv['energy_kcal'], false),
        ]),
        _buildNutrientSection(context, 'Macronutrients', Icons.restaurant_rounded, [
          _nutrientBar('Total fat', serving['total_fat'], per100['total_fat'],
              dv['total_fat'], true),
          _nutrientBar('Saturated fat', serving['saturated_fat'],
              per100['saturated_fat'], dv['saturated_fat'], true),
          _nutrientBar('Trans fat', serving['trans_fat'], per100['trans_fat'],
              dv['trans_fat'], true),
          _nutrientBar('Carbohydrates', serving['total_carbohydrate'],
              per100['total_carbohydrate'], dv['total_carbohydrate'], false),
          _nutrientBar(
              'Fiber', serving['fiber'], per100['fiber'], dv['fiber'], false),
          _nutrientBar('Total sugars', serving['sugar'], per100['sugar'],
              dv['total_sugars'], true),
          _nutrientBar('Added sugars', serving['added_sugar'],
              per100['added_sugar'], dv['added_sugars'], true),
          _nutrientBar('Protein', serving['protein'], per100['protein'],
              dv['protein'], false),
        ]),
        _buildNutrientSection(context, 'Other Nutrients', Icons.science_rounded, [
          _nutrientBar('Sodium', serving['sodium'], per100['sodium'],
              dv['sodium'], true),
          _nutrientBar('Cholesterol', serving['cholesterol'],
              per100['cholesterol'], dv['cholesterol'], true),
          _nutrientBar('Calcium', serving['calcium'], per100['calcium'],
              dv['calcium'], false),
          _nutrientBar(
              'Iron', serving['iron'], per100['iron'], dv['iron'], false),
          _nutrientBar('Potassium', serving['potassium'], per100['potassium'],
              dv['potassium'], false),
        ]),
        if (scoring.isNotEmpty)
          _buildAssessments(context, scoring, classification),
        _buildIngredientsCard(context, ingredients, allergens),
        if (findings.isNotEmpty)
          _buildFindingsCard(context, health, findings),
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
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.06),
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
                errorBuilder: (_, __, ___) => Center(
                  child: Icon(Icons.image_not_supported_outlined,
                      size: 48, color: Colors.grey.shade400),
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
                      _infoPill(Icons.storefront_outlined, product['brands'].toString()),
                    if (_text(product['barcode'] ?? requestedBarcode) != 'Not available')
                      _infoPill(Icons.qr_code, (product['barcode'] ?? requestedBarcode).toString()),
                    if (_text(product['categories']) != 'Not available')
                      _infoPill(Icons.category_outlined, product['categories'].toString()),
                    if (_text(normServing['text']) != 'Not available')
                      _infoPill(Icons.straighten, normServing['text'].toString()),
                  ],
                ),
                if (_text(_map(analysis['data_quality'])['status']) != 'Not available') ...[
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Icon(Icons.verified_outlined,
                          size: 14, color: Colors.grey.shade500),
                      const SizedBox(width: 4),
                      Text(
                        'Data quality: ${_map(analysis['data_quality'])['status']}',
                        style: TextStyle(
                            fontSize: 12, color: Colors.grey.shade500),
                      ),
                    ],
                  ),
                ],
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
            child: Text(text,
                style: const TextStyle(fontSize: 12, color: AppTheme.textMedium),
                overflow: TextOverflow.ellipsis),
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
  ) {
    final scores = _map(scoring['scores']);
    final overall = scores['overall'];
    final grade = _text(scores['grade']);
    final gradeLabel = _text(scores['grade_label']);
    final nutriScore = classification['nutriscore_grade']?.toString();

    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.05),
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
                  child: const Text('N/A',
                      style: TextStyle(
                          fontSize: 22,
                          fontWeight: FontWeight.w600,
                          color: AppTheme.textLight)),
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
                            horizontal: 12, vertical: 4),
                        decoration: BoxDecoration(
                          color: AppTheme.gradeColor(grade).withOpacity(0.12),
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
                    const SizedBox(height: 10),
                    Text(
                      _text(scoring['explanation']),
                      style: const TextStyle(
                          fontSize: 12,
                          height: 1.4,
                          color: AppTheme.textLight),
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
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
        final color = AppTheme.nutriScoreColors[l.toLowerCase()] ??
            AppTheme.textLight;
        return Container(
          margin: const EdgeInsets.only(right: 3),
          width: isActive ? 30 : 24,
          height: isActive ? 30 : 24,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: isActive ? color : color.withOpacity(0.15),
            borderRadius: BorderRadius.circular(6),
            boxShadow: isActive
                ? [BoxShadow(color: color.withOpacity(0.4), blurRadius: 6)]
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

  // --- Nutrient section ---
  Widget _buildNutrientSection(
      BuildContext context, String title, IconData icon, List<Widget> children) {
    final visible = children.whereType<NutrientBar>().where((c) {
      return c.servingValue.isNotEmpty || c.per100Value.isNotEmpty;
    }).toList();
    if (visible.isEmpty) return const SizedBox.shrink();

    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: Colors.grey.shade200),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: AppTheme.primaryGreen.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(icon, color: AppTheme.primaryGreen, size: 18),
              ),
              const SizedBox(width: 10),
              Text(title,
                  style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                      color: AppTheme.textDark)),
            ],
          ),
          const SizedBox(height: 12),
          ...visible,
        ],
      ),
    );
  }

  Widget _nutrientBar(String name, Object? servingRaw, Object? per100Raw,
      Object? dvPercent, bool isLimit) {
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
  ) {
    final scores = _map(scoring['scores']);
    final sufficiency = _map(scoring['data_sufficiency']);
    final limits = _map(scores['nutrient_limits']);
    final nova = _map(scores['nova_processing']);
    final additives = _map(scores['additive_safety']);
    final trafficLights = _map(limits['traffic_lights']);
    final missing = _list(sufficiency['missing']);
    final unavailable = _list(sufficiency['unavailable_components']);

    return Column(
      children: [
        // Nutri-Score card
        _assessmentCard(
          context,
          icon: Icons.grade_rounded,
          title: 'Nutri-Score',
          color: AppTheme.gradeColor(
              classification['nutriscore_grade']?.toString()),
          children: [
            if (classification['nutriscore_grade'] != null) ...[
              _buildNutriScoreVisual(
                  classification['nutriscore_grade'].toString()),
              const SizedBox(height: 8),
            ],
            Text(
              classification['nutriscore_grade'] == null
                  ? 'Unavailable: Open Food Facts did not report a Nutri-Score grade.'
                  : 'Reported: ${classification['nutriscore_grade']} (Open Food Facts)',
              style: const TextStyle(fontSize: 13, color: AppTheme.textMedium),
            ),
            Text(
              'Algorithm: ${_text(_map(classification['nutriscore'])['reported_algorithm_version'])}',
              style: const TextStyle(fontSize: 12, color: AppTheme.textLight),
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
            Text(_text(limits['details']),
                style: const TextStyle(
                    fontSize: 12, color: AppTheme.textLight)),
            const SizedBox(height: 10),
            ...['total_fat', 'saturated_fat', 'sugar', 'salt'].map((key) {
              final item = _map(trafficLights[key]);
              if (item.isEmpty) return const SizedBox.shrink();
              final color = AppTheme.trafficLightColor(
                  item['color']?.toString());
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
                              color: color.withOpacity(0.4), blurRadius: 4)
                        ],
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        '${key.replaceAll('_', ' ').toUpperCase()}: '
                        '${item['value'] == null ? 'unavailable' : '${_number(item['value'])} ${item['unit']}'}'
                        ' — ${_text(item['color'])}',
                        style: const TextStyle(
                            fontSize: 13, color: AppTheme.textMedium),
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
            if (nova['nova_group'] is num) ...[
              _buildNovaVisual((nova['nova_group'] as num).toInt()),
              const SizedBox(height: 8),
            ],
            Text(
              nova['nova_group'] == null
                  ? 'Unavailable: ${_text(nova['details'])}'
                  : 'Group ${nova['nova_group']} (${_text(nova['source'])})',
              style: const TextStyle(fontSize: 13, color: AppTheme.textMedium),
            ),
            Text(_text(nova['details']),
                style: const TextStyle(
                    fontSize: 12, color: AppTheme.textLight)),
            if (_list(nova['markers_found']).isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                    'Markers: ${_list(nova['markers_found']).join(', ')}',
                    style: const TextStyle(
                        fontSize: 12, color: AppTheme.textLight)),
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
            Text('Status: ${_text(additives['status'])}',
                style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                    color: AppTheme.textMedium)),
            Text(_text(additives['details']),
                style: const TextStyle(
                    fontSize: 12, color: AppTheme.textLight)),
            ..._list(additives['flagged_additives']).map((i) => Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Row(
                    children: [
                      const Icon(Icons.warning_amber_rounded,
                          size: 14, color: Color(0xFFE65100)),
                      const SizedBox(width: 6),
                      Expanded(
                          child: Text(_text(i),
                              style: const TextStyle(
                                  fontSize: 12, color: AppTheme.textMedium))),
                    ],
                  ),
                )),
          ],
        ),
        // Overall score details
        _assessmentCard(
          context,
          icon: Icons.analytics_outlined,
          title: 'Score Breakdown',
          color: AppTheme.primaryGreen,
          children: [
            Text(_text(scoring['explanation']),
                style: const TextStyle(
                    fontSize: 13, height: 1.4, color: AppTheme.textMedium)),
            const SizedBox(height: 6),
            Text(
              'Formula: ${_text(scoring['formula_version'])}; data sufficiency: '
              '${_text(sufficiency['status'])}${missing.isEmpty ? '' : ' (${missing.join(', ')})'}',
              style:
                  const TextStyle(fontSize: 12, color: AppTheme.textLight),
            ),
            Text(
              'Nutrition completeness: ${_text(_map(sufficiency['nutrition'])['status'])}; '
              'reliability: ${_text(sufficiency['score_confidence'])}.',
              style:
                  const TextStyle(fontSize: 12, color: AppTheme.textLight),
            ),
            if (unavailable.isNotEmpty)
              Text(
                'Unavailable components: ${unavailable.join(', ')}.',
                style:
                    const TextStyle(fontSize: 12, color: AppTheme.textLight),
              ),
            const SizedBox(height: 4),
            Text(
              'This is NutriTrust’s custom comparison score, not an official government or Nutri-Score rating.',
              style: TextStyle(
                  fontSize: 11,
                  fontStyle: FontStyle.italic,
                  color: Colors.grey.shade500),
            ),
          ],
        ),
      ],
    );
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
            color: isActive ? color : color.withOpacity(0.12),
            borderRadius: BorderRadius.circular(8),
            boxShadow: isActive
                ? [BoxShadow(color: color.withOpacity(0.4), blurRadius: 6)]
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
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: Colors.grey.shade200),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: color.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(icon, color: color, size: 18),
              ),
              const SizedBox(width: 10),
              Text(title,
                  style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                      color: AppTheme.textDark)),
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
          Text('Ingredients',
              style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  color: Colors.grey.shade600)),
          const SizedBox(height: 4),
          Text(ingredients['text'].toString(),
              style: const TextStyle(
                  fontSize: 13, height: 1.4, color: AppTheme.textMedium)),
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
                    fontSize: 13, color: AppTheme.textMedium),
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
                const Icon(Icons.info_outline, size: 14, color: AppTheme.textLight),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    'May contain: ${_map(allergens['precautionary_traces'])['text']}',
                    style: const TextStyle(
                        fontSize: 12, color: AppTheme.textLight),
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }

  // --- Findings card ---
  Widget _buildFindingsCard(
    BuildContext context,
    Map<String, dynamic> health,
    Iterable<Map> findings,
  ) {
    return _assessmentCard(
      context,
      icon: Icons.search_rounded,
      title: 'Data Quality & Findings',
      color: const Color(0xFF455A64),
      children: [
        Text('Ruleset: ${_text(_map(health['ruleset'])['scope'])}',
            style:
                const TextStyle(fontSize: 12, color: AppTheme.textLight)),
        const SizedBox(height: 8),
        ...findings.map((item) => Container(
              margin: const EdgeInsets.only(bottom: 8),
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: Colors.grey.shade50,
                borderRadius: BorderRadius.circular(10),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    margin: const EdgeInsets.only(top: 2),
                    padding: const EdgeInsets.symmetric(
                        horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: Colors.grey.shade200,
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(
                      _text(item['category']),
                      style: const TextStyle(
                          fontSize: 10,
                          fontWeight: FontWeight.w600,
                          color: AppTheme.textMedium),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(_text(item['id']),
                            style: const TextStyle(
                                fontSize: 13,
                                fontWeight: FontWeight.w600,
                                color: AppTheme.textDark)),
                        const SizedBox(height: 2),
                        Text(_text(item['explanation']),
                            style: const TextStyle(
                                fontSize: 12, color: AppTheme.textLight)),
                      ],
                    ),
                  ),
                ],
              ),
            )),
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
          .map((w) => Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('• ',
                        style: TextStyle(color: Color(0xFFE65100))),
                    Expanded(
                      child: Text(_text(w),
                          style: const TextStyle(
                              fontSize: 13, color: AppTheme.textMedium)),
                    ),
                  ],
                ),
              ))
          .toList(),
    );
  }
}
