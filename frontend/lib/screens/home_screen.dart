import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:openfoodfacts/openfoodfacts.dart';

import '../services/open_food_facts_service.dart';
import 'barcode_scanner_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final ImagePicker _picker = ImagePicker();
  final OpenFoodFactsService _productService = OpenFoodFactsService();

  File? _labelImage;
  Product? _product;
  bool _isLoading = false;
  String? _error;

  Future<void> _pickImage(ImageSource source) async {
    try {
      final image = await _picker.pickImage(source: source, imageQuality: 90);

      if (image == null || !mounted) return;

      setState(() {
        _labelImage = File(image.path);
        _product = null;
        _error = null;
      });
    } catch (error) {
      if (!mounted) return;

      setState(() {
        _error = 'Unable to select image: $error';
      });
    }
  }

  Future<void> _scanBarcode() async {
    try {
      final barcode = await Navigator.of(context).push<String>(
        MaterialPageRoute(builder: (_) => const BarcodeScannerScreen()),
      );

      if (barcode == null || !mounted) return;

      await _lookupProduct(barcode);
    } catch (error) {
      if (!mounted) return;

      setState(() {
        _error = 'Unable to scan barcode: $error';
      });
    }
  }

  Future<void> _lookupProduct(String barcode) async {
    setState(() {
      _isLoading = true;
      _product = null;
      _error = null;
    });

    try {
      final result = await _productService.getProductByBarcode(barcode);

      if (!mounted) return;

      setState(() {
        _product = result;

        if (result == null) {
          _error =
              'Product not found in Open Food Facts. '
              'Try another barcode or upload the food label.';
        }
      });
    } catch (error) {
      if (!mounted) return;

      setState(() {
        _error = error.toString().replaceFirst('Exception: ', '');
      });
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  String _nutrientValue(Product product, Nutrient nutrientType, String unit) {
    final value = product.nutriments?.getValue(
      nutrientType,
      PerSize.oneHundredGrams,
    );

    return value == null ? 'Not available' : '$value $unit';
  }

  Widget _buildProductResult(Product product) {
    final ingredients = product.ingredientsText?.trim();
    final allergens = product.allergens?.names;
    final productName = product.productName?.trim();

    return Card(
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (product.imageFrontUrl != null &&
                product.imageFrontUrl!.isNotEmpty) ...[
              Center(
                child: Image.network(
                  product.imageFrontUrl!,
                  height: 150,
                  fit: BoxFit.contain,
                  errorBuilder: (_, __, ___) => const SizedBox.shrink(),
                ),
              ),
              const SizedBox(height: 12),
            ],
            Text(
              productName?.isNotEmpty == true
                  ? productName!
                  : 'Unknown product',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 4),
            Text('Brand: ${product.brands ?? 'Unknown brand'}'),
            Text('Barcode: ${product.barcode ?? 'Not available'}'),
            const Divider(height: 28),

            Text('Ingredients', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 6),
            Text(
              ingredients?.isNotEmpty == true
                  ? ingredients!
                  : 'Ingredients not available in the database.',
            ),

            const SizedBox(height: 20),
            Text(
              'Nutrition per 100 g',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            _nutritionRow(
              'Energy',
              _nutrientValue(product, Nutrient.energyKCal, 'kcal'),
            ),
            _nutritionRow(
              'Sugar',
              _nutrientValue(product, Nutrient.sugars, 'g'),
            ),
            _nutritionRow(
              'Total fat',
              _nutrientValue(product, Nutrient.fat, 'g'),
            ),
            _nutritionRow(
              'Saturated fat',
              _nutrientValue(product, Nutrient.saturatedFat, 'g'),
            ),
            _nutritionRow(
              'Protein',
              _nutrientValue(product, Nutrient.proteins, 'g'),
            ),
            _nutritionRow('Salt', _nutrientValue(product, Nutrient.salt, 'g')),

            const Divider(height: 28),
            Text(
              'Allergens: '
              '${allergens == null || allergens.isEmpty ? 'Not listed' : allergens.join(', ')}',
            ),
            const SizedBox(height: 6),
            Text(
              'Nutrition grade: '
              '${product.nutriscore ?? 'Not available'}',
            ),
          ],
        ),
      ),
    );
  }

  Widget _nutritionRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(child: Text(label)),
          const SizedBox(width: 12),
          Flexible(child: Text(value, textAlign: TextAlign.end)),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('NutriTrust'), centerTitle: true),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Text(
              'Understand what you eat.',
              style: Theme.of(context).textTheme.headlineMedium,
            ),
            const SizedBox(height: 8),
            const Text(
              'Scan a product barcode or upload its food label '
              'to explore its ingredients and nutrition.',
            ),
            const SizedBox(height: 24),

            SizedBox(
              height: 54,
              child: FilledButton.icon(
                onPressed: _isLoading ? null : _scanBarcode,
                icon: const Icon(Icons.qr_code_scanner),
                label: const Text('Scan product barcode'),
              ),
            ),
            const SizedBox(height: 12),

            SizedBox(
              height: 54,
              child: OutlinedButton.icon(
                onPressed: _isLoading
                    ? null
                    : () => _pickImage(ImageSource.camera),
                icon: const Icon(Icons.camera_alt_outlined),
                label: const Text('Take a label photo'),
              ),
            ),
            const SizedBox(height: 12),

            SizedBox(
              height: 54,
              child: OutlinedButton.icon(
                onPressed: _isLoading
                    ? null
                    : () => _pickImage(ImageSource.gallery),
                icon: const Icon(Icons.photo_library_outlined),
                label: const Text('Choose from gallery'),
              ),
            ),

            if (_labelImage != null) ...[
              const SizedBox(height: 20),
              ClipRRect(
                borderRadius: BorderRadius.circular(12),
                child: Image.file(
                  _labelImage!,
                  height: 220,
                  fit: BoxFit.contain,
                ),
              ),
              const SizedBox(height: 8),
              const Text('Image selected. OCR processing will be added next.'),
            ],

            if (_isLoading) ...[
              const SizedBox(height: 24),
              const Center(child: CircularProgressIndicator()),
              const SizedBox(height: 12),
              const Center(child: Text('Looking up product...')),
            ],

            if (_error != null) ...[
              const SizedBox(height: 20),
              Text(
                _error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
              const SizedBox(height: 8),
              if (!_isLoading)
                TextButton.icon(
                  onPressed: _scanBarcode,
                  icon: const Icon(Icons.refresh),
                  label: const Text('Scan another barcode'),
                ),
            ],

            if (_product != null) ...[
              const SizedBox(height: 24),
              _buildProductResult(_product!),
            ],
          ],
        ),
      ),
    );
  }
}
