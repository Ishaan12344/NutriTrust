import 'dart:io';
import 'dart:typed_data';
import 'dart:developer' as developer;

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../models/health_profile.dart';
import '../services/nutritrust_api_service.dart';
import '../widgets/personalized_insights.dart';
import 'barcode_scanner_screen.dart';
import 'personal_health_input_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, this.profile});

  final HealthProfile? profile;
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final ImagePicker _picker = ImagePicker();
  final NutriTrustApiService _api = NutriTrustApiService();
  File? _labelImage;
  Map<String, dynamic>? _analysis;
  bool _isLoading = false;
  String? _error;

  @override
  void dispose() { _api.close(); super.dispose(); }

  Future<void> _pickImage(ImageSource source) async {
    try {
      final image = await _picker.pickImage(source: source, imageQuality: 90);
      developer.log('image picker returned: ${image?.name ?? 'cancelled'}', name: 'nutritrust.ui');
      if (image == null || !mounted) return;
      final file = File(image.path);
      final size = await file.length();
      developer.log('image selected: name=${image.name} size=$size type=${image.mimeType ?? 'unknown'}', name: 'nutritrust.ui');
      if (size > 10 * 1024 * 1024) {
        setState(() => _error = 'Choose an image that is 10 MB or smaller.');
        return;
      }
      final extension = image.name.toLowerCase().split('.').last;
      if (!{'jpg', 'jpeg', 'png'}.contains(extension)) {
        setState(() => _error = 'Upload a JPG, JPEG, or PNG image.');
        return;
      }
      setState(() { _labelImage = file; _analysis = null; _error = null; });
      await _analyzeImage();
    } catch (_) { if (mounted) setState(() => _error = 'Unable to select that image.'); }
  }

  Future<void> _analyzeImage() async {
    final file = _labelImage;
    if (file == null || _isLoading) return;
    developer.log('label callback triggered; api=${_api.baseUrl}', name: 'nutritrust.ui');
    setState(() { _isLoading = true; _error = null; });
    try {
      final bytes = await file.readAsBytes();
      final name = file.path.split(Platform.pathSeparator).last;
      final response = await _api.analyzeLabel(
        imageBytes: Uint8List.fromList(bytes), filename: name,
        contentType: name.toLowerCase().endsWith('.png') ? 'image/png' : 'image/jpeg',
      );
      if (mounted) setState(() => _analysis = response);
    } on NutriTrustApiException catch (error) {
      developer.log('label UI error', name: 'nutritrust.ui', error: error);
      if (mounted) setState(() => _error = error.message);
    } catch (error, stackTrace) {
      developer.log('label unexpected UI error', name: 'nutritrust.ui', error: error, stackTrace: stackTrace);
      if (mounted) setState(() => _error = 'The label could not be analyzed. Please retry.');
    }
    finally { if (mounted) setState(() => _isLoading = false); }
  }

  Future<void> _scanBarcode() async {
    developer.log('barcode button triggered; api=${_api.baseUrl}', name: 'nutritrust.ui');
    if (mounted) setState(() { _labelImage = null; _error = null; });
    String? barcode;
    try {
      barcode = await Navigator.of(context).push<String>(MaterialPageRoute(builder: (_) => const BarcodeScannerScreen()));
    } catch (error, stackTrace) {
      developer.log('scanner navigation failure', name: 'nutritrust.ui', error: error, stackTrace: stackTrace);
      if (mounted) setState(() => _error = 'The barcode scanner could not start. Please retry.');
      return;
    }
    developer.log('scanner returned barcode=${barcode ?? 'none'}', name: 'nutritrust.ui');
    if (barcode == null || !mounted || _isLoading) return;
    setState(() { _isLoading = true; _analysis = null; _labelImage = null; _error = null; });
    try {
      final response = await _api.analyzeBarcode(barcode);
      if (mounted) setState(() => _analysis = response);
    } on NutriTrustApiException catch (error) {
      developer.log('barcode UI error', name: 'nutritrust.ui', error: error);
      if (mounted) setState(() => _error = error.message);
    } catch (error, stackTrace) {
      developer.log('barcode unexpected UI error', name: 'nutritrust.ui', error: error, stackTrace: stackTrace);
      if (mounted) setState(() => _error = 'The barcode lookup failed. Please retry.');
    }
    finally { if (mounted) setState(() => _isLoading = false); }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('NutriTrust'), centerTitle: true),
    body: SafeArea(child: ListView(padding: const EdgeInsets.all(20), children: [
      Text('Understand what you eat.', style: Theme.of(context).textTheme.headlineMedium),
      const SizedBox(height: 8),
      const Text('Scan a product barcode or upload its food label to explore its ingredients and nutrition.'),
      const SizedBox(height: 12),
      OutlinedButton.icon(
        onPressed: () => Navigator.of(context).push(
          MaterialPageRoute(builder: (_) => PersonalHealthInputScreen(initialProfile: widget.profile)),
        ),
        icon: const Icon(Icons.tune),
        label: Text(widget.profile?.hasInformation == true ? 'Edit nutrition preferences' : 'Personalize your nutrition'),
      ),
      const SizedBox(height: 24),
      FilledButton.icon(onPressed: _isLoading ? null : _scanBarcode, icon: const Icon(Icons.qr_code_scanner), label: const Text('Scan product barcode')),
      const SizedBox(height: 12),
      OutlinedButton.icon(onPressed: _isLoading ? null : () => _pickImage(ImageSource.camera), icon: const Icon(Icons.camera_alt_outlined), label: const Text('Take a label photo')),
      const SizedBox(height: 12),
      OutlinedButton.icon(onPressed: _isLoading ? null : () => _pickImage(ImageSource.gallery), icon: const Icon(Icons.photo_library_outlined), label: const Text('Choose from gallery')),
      if (_labelImage != null) ...[
        const SizedBox(height: 16),
        ClipRRect(borderRadius: BorderRadius.circular(12), child: Image.file(_labelImage!, height: 220, fit: BoxFit.contain)),
        const SizedBox(height: 10),
        FilledButton.icon(onPressed: _isLoading ? null : _analyzeImage, icon: const Icon(Icons.document_scanner_outlined), label: const Text('Analyze label')),
      ],
      if (_isLoading) const Padding(padding: EdgeInsets.all(24), child: Column(children: [CircularProgressIndicator(), SizedBox(height: 12), Text('Analyzing…')])),
      if (_error != null) ...[
        const SizedBox(height: 20), Text(_error!, style: TextStyle(color: Colors.red)),
        TextButton.icon(onPressed: _labelImage == null ? _scanBarcode : _analyzeImage, icon: const Icon(Icons.refresh), label: const Text('Retry')),
      ],
      if (_analysis != null) ...[const SizedBox(height: 24), NutritionReport(response: _analysis!, profile: widget.profile)],
    ])),
  );
}

class NutritionReport extends StatelessWidget {
  const NutritionReport({super.key, required this.response, this.profile});
  final Map<String, dynamic> response;
  final HealthProfile? profile;
  Map<String, dynamic> _map(Object? value) => value is Map ? Map<String, dynamic>.from(value) : <String, dynamic>{};
  List<Object?> _list(Object? value) => value is List ? value : <Object?>[];
  String _text(Object? value) => value == null || value.toString().trim().isEmpty ? 'Not available' : value.toString();
  String _number(Object? value) => value is num ? (value % 1 == 0 ? value.toInt().toString() : value.toString()) : _text(value);

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
    final warnings = [..._list(analysis['warnings']), ..._list(analysis['missing_data_warnings'])];
    final requestedBarcode = _map(analysis['identification'])['requested_barcode'];
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (_text(product['image_front_url']) != 'Not available')
        ClipRRect(
          borderRadius: BorderRadius.circular(12),
          child: Image.network(
            product['image_front_url'].toString(),
            height: 180,
            fit: BoxFit.contain,
            errorBuilder: (_, __, ___) => const SizedBox.shrink(),
          ),
        ),
      Text(_text(product['name']), style: Theme.of(context).textTheme.headlineSmall),
      if (_text(product['brands']) != 'Not available') Text('Brand: ${product['brands']}'),
      if (_text(product['barcode'] ?? requestedBarcode) != 'Not available') Text('Barcode: ${product['barcode'] ?? requestedBarcode}'),
      if (_text(product['categories']) != 'Not available') Text('Category: ${product['categories']}'),
      if (_text(normServing['text']) != 'Not available') Text('Serving size: ${normServing['text']}'),
      if (_text(_map(analysis['data_quality'])['status']) != 'Not available')
        Text('Data quality: ${_map(analysis['data_quality'])['status']}'),
      const SizedBox(height: 16),
      if (profile?.hasInformation == true) ...[
        PersonalizedInsights(profile: profile!, analysis: analysis),
        const SizedBox(height: 12),
      ],
      _section(context, 'Energy', [_metric('Calories', serving['energy_kcal'], per100['energy_kcal'], dv['energy_kcal'])]),
      _section(context, 'Macronutrients', [
        _metric('Total fat', serving['total_fat'], per100['total_fat'], dv['total_fat']),
        _metric('Saturated fat', serving['saturated_fat'], per100['saturated_fat'], dv['saturated_fat']),
        _metric('Trans fat', serving['trans_fat'], per100['trans_fat'], dv['trans_fat']),
        _metric('Carbohydrates', serving['total_carbohydrate'], per100['total_carbohydrate'], dv['total_carbohydrate']),
        _metric('Fiber', serving['fiber'], per100['fiber'], dv['fiber']),
        _metric('Total sugars', serving['sugar'], per100['sugar'], dv['total_sugars']),
        _metric('Added sugars', serving['added_sugar'], per100['added_sugar'], dv['added_sugars']),
        _metric('Protein', serving['protein'], per100['protein'], dv['protein']),
      ]),
      _section(context, 'Other nutrients', [
        _metric('Sodium', serving['sodium'], per100['sodium'], dv['sodium']),
        _metric('Cholesterol', serving['cholesterol'], per100['cholesterol'], dv['cholesterol']),
        _metric('Calcium', serving['calcium'], per100['calcium'], dv['calcium']),
        _metric('Iron', serving['iron'], per100['iron'], dv['iron']),
        _metric('Potassium', serving['potassium'], per100['potassium'], dv['potassium']),
      ]),
      if (scoring.isNotEmpty) _buildBarcodeAssessmentSections(context, scoring, classification),
      _section(context, 'Ingredients and allergens', [
        if (_text(ingredients['text']) != 'Not available') Text('Ingredients: ${ingredients['text']}'),
        Text('Declared allergens: ${_list(allergens['declared']).isEmpty ? 'Unknown — no declaration was identified' : _list(allergens['declared']).join(', ')}'),
        if (_text(_map(allergens['precautionary_traces'])['text']) != 'Not available')
          Text('May contain: ${_map(allergens['precautionary_traces'])['text']}'),
      ]),
      _section(context, 'Data quality and missing information', [
        const Text('Nutrient observations and label findings; the NutriTrust composite score is shown separately.'),
        Text('Ruleset: ${_text(_map(health['ruleset'])['scope'])}'),
        ...findings.map((item) => ListTile(contentPadding: EdgeInsets.zero, title: Text(_text(item['id'])), subtitle: Text(_text(item['explanation'])), trailing: Text(_text(item['category'])))),
      ]),
      if (warnings.isNotEmpty) _section(context, 'Data quality and warnings', warnings.map((w) => Text('• ${_text(w)}')).toList()),
    ]);
  }

  Widget _section(BuildContext context, String title, List<Widget> children) {
    final visible = children.where((child) =>
        child is! SizedBox || child.width != 0 || child.height != 0 || child.child != null).toList();
    if (visible.isEmpty) return const SizedBox.shrink();
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          ...visible,
        ]),
      ),
    );
  }

  /// Renders server-calculated barcode assessments in the user-facing order.
  /// No score is recomputed in Flutter.
  Widget _buildBarcodeAssessmentSections(
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
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _section(context, 'Nutri-Score (reported)', [
        Text(classification['nutriscore_grade'] == null
            ? 'Unavailable: Open Food Facts did not report a Nutri-Score grade.'
            : 'Reported Nutri-Score: ${classification['nutriscore_grade']} (Open Food Facts)'),
        Text('Algorithm version: ${_text(_map(classification['nutriscore'])['reported_algorithm_version'])}'),
        const Text('Source: Open Food Facts. NutriTrust does not calculate an official Nutri-Score.'),
      ]),
      _section(context, 'UK Traffic Light System', [
        Text(_text(limits['details'])),
        ...['total_fat', 'saturated_fat', 'sugar', 'salt'].map((key) {
          final item = _map(trafficLights[key]);
          if (item.isEmpty) return Text('${key.replaceAll('_', ' ')}: unavailable');
          final thresholds = _map(item['thresholds']);
          final thresholdText = thresholds.isEmpty
              ? ''
              : '; green <= ${thresholds['green']}, amber <= ${thresholds['amber']} ${item['unit']}';
          return Text('${key.replaceAll('_', ' ')}: ${item['value'] == null ? 'unavailable' : '${_number(item['value'])} ${item['unit']}'} — ${_text(item['color'])}$thresholdText');
        }),
      ]),
      _section(context, 'NOVA Classification', [
        Text(nova['nova_group'] == null
            ? 'Unavailable: ${_text(nova['details'])}'
            : 'Group ${nova['nova_group']} (${_text(nova['source'])})'),
        Text(_text(nova['details'])),
        if (_list(nova['markers_found']).isNotEmpty)
          Text('Observed markers: ${_list(nova['markers_found']).join(', ')}'),
      ]),
      _section(context, 'Additive Safety Analysis', [
        Text('Status: ${_text(additives['status'])}'),
        Text(_text(additives['details'])),
        ..._list(additives['flagged_additives']).map((item) => Text(_text(item))),
      ]),
      _section(context, 'Overall NutriTrust Score', [
        Text('Overall: ${scores['overall'] == null ? 'Not calculated' : '${_number(scores['overall'])}/100'}'),
        Text('Grade: ${_text(scores['grade'])} — ${_text(scores['grade_label'])}'),
        Text(_text(scoring['explanation'])),
        Text('Formula: ${_text(scoring['formula_version'])}; data sufficiency: ${_text(sufficiency['status'])}${missing.isEmpty ? '' : ' (${missing.join(', ')})'}'),
        Text('Nutrition completeness: ${_text(_map(sufficiency['nutrition'])['status'])}; reliability: ${_text(sufficiency['score_confidence'])}.'),
        if (unavailable.isNotEmpty)
          Text('Unavailable score components: ${unavailable.join(', ')}. Available components were reweighted.'),
        const Text('This is NutriTrust’s custom comparison score, not an official government or Nutri-Score rating.'),
      ]),
    ]);
  }

  Widget _buildScoringSection(BuildContext context, Map<String, dynamic> scoring, Map<String, dynamic> classification) {
    final scores = _map(scoring['scores']);
    final sufficiency = _map(scoring['data_sufficiency']);
    final nova = _map(scores['nova_processing']);
    final limits = _map(scores['nutrient_limits']);
    final additives = _map(scores['additive_safety']);
    final trafficLights = _map(limits['traffic_lights']);
    final missing = _list(sufficiency['missing']);
    final status = _text(sufficiency['status']);
    final overall = scores['overall'];
    return _section(context, 'NutriTrust score', [
      Text('Overall: ${overall == null ? 'Not calculated' : '${_number(overall)}/100'}'),
      Text('Grade: ${_text(scores['grade'])} — ${_text(scores['grade_label'])}'),
      Text(_text(scoring['explanation'])),
      Text('Formula: ${_text(scoring['formula_version'])}'),
      Text('Data sufficiency: $status${missing.isEmpty ? '' : ' (${missing.join(', ')})'}'),
      Text('Nutrition completeness: ${_text(_map(sufficiency['nutrition'])['status'])}; reliability: ${_text(sufficiency['score_confidence'])}.'),
      ExpansionTile(
        tilePadding: EdgeInsets.zero,
        title: const Text('Custom nutrient-quality assessment'),
        subtitle: Text('NutriTrust contribution: ${_number(_map(scores['nutrient_quality'])['score'])}/100'),
        children: [Text(_text(_map(scores['nutrient_quality'])['details']))],
      ),
      ExpansionTile(
        tilePadding: EdgeInsets.zero,
        title: const Text('NOVA processing assessment'),
        subtitle: Text(nova['nova_group'] == null ? 'Unavailable' : 'Group ${nova['nova_group']} (${_text(nova['source'])})'),
        children: [Text(_text(nova['details'])), if (_list(nova['markers_found']).isNotEmpty) Text('Observed markers: ${_list(nova['markers_found']).join(', ')}')],
      ),
      ExpansionTile(
        tilePadding: EdgeInsets.zero,
        title: const Text('UK front-of-pack traffic lights'),
        subtitle: Text(_text(limits['details'])),
        children: [
          ...trafficLights.entries.map((entry) {
            final item = _map(entry.value);
            final thresholds = _map(item['thresholds']);
            final bands = thresholds.isEmpty ? '' : ' (green ≤ ${thresholds['green']}, amber ≤ ${thresholds['amber']} ${item['unit']})';
            return ListTile(contentPadding: EdgeInsets.zero,
              title: Text('${entry.key}: ${item['value'] == null ? 'unavailable' : '${_number(item['value'])} ${item['unit']}'}'),
              subtitle: Text('${_text(item['color'])}$bands; ${item['verified'] == true ? 'verified input' : 'unverified'}'));
          }),
          if (_map(limits['energy_reference'])['value'] != null)
            Text('Energy: ${_number(_map(limits['energy_reference'])['value'])} kJ/100 g; no traffic-light color is assigned.'),
        ],
      ),
      ExpansionTile(
        tilePadding: EdgeInsets.zero,
        title: const Text('Additive analysis'),
        subtitle: Text('Status: ${_text(additives['status'])}; NutriTrust contribution: ${_number(additives['score'])}/100'),
        children: [Text(_text(additives['details'])), ..._list(additives['flagged_additives']).map((item) => Text(_text(item)))],
      ),
      ExpansionTile(
        tilePadding: EdgeInsets.zero,
        title: const Text('Nutri-Score (reported)'),
        subtitle: Text(_text(classification['nutriscore_grade'])),
        children: [const Text('Source: Open Food Facts. NutriTrust does not calculate the official Nutri-Score.')],
      ),
      ExpansionTile(
        tilePadding: EdgeInsets.zero,
        title: const Text('How was this calculated?'),
        children: [
          Text('Policy ${_text(scoring['formula_version'])}; configured weights: ${_map(scoring['weights'])}'),
          Text('Component scores: ${_map(scoring['component_scores'])}'),
          Text('Weighted contributions: ${_map(scoring['contributions'])}'),
          Text('Reported Nutri-Score: ${_text(classification['nutriscore_grade'])} (Open Food Facts). NutriTrust’s nutrient-quality value is custom and is not the official Nutri-Score.'),
          if (_list(_map(sufficiency['nutrition'])['missing_fields']).isNotEmpty)
            Text('Nutrition fields unavailable: ${_list(_map(sufficiency['nutrition'])['missing_fields']).join(', ')}'),
        ],
      ),
    ]);
  }

  Widget _metric(String name, Object? serving, Object? per100, Object? percent) {
    final s = _nutrient(serving);
    final p = _nutrient(per100);
    if (s.isEmpty && p.isEmpty) return const SizedBox.shrink();
    final parts = <String>[];
    if (s.isNotEmpty) parts.add('Per serving: $s');
    if (p.isNotEmpty) parts.add('Per 100 g: $p');
    if (percent != null) parts.add('Label DV: ${_number(percent)}%');
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Text('$name: ${parts.join(' · ')}'),
    );
  }
  String _nutrient(Object? value) {
    final item = _map(value);
    if (item.isEmpty || item['value'] is! num || item['unit'] == null) return '';
    final qualifier = item['status'] == 'approximate' ? '~' : '';
    return '$qualifier${_number(item['value'])} ${_text(item['unit'])}';
  }
}
