import 'package:openfoodfacts/openfoodfacts.dart';

class OpenFoodFactsService {
  Future<Product?> getProductByBarcode(String barcode) async {
    final normalizedBarcode = barcode.trim();

    // Keep the barcode as a String to preserve leading zeros.
    if (!RegExp(r'^\d{8,14}$').hasMatch(normalizedBarcode)) {
      throw const FormatException(
        'Invalid barcode. Please scan the product barcode again.',
      );
    }

    final configuration = ProductQueryConfiguration(
      normalizedBarcode,
      version: ProductQueryVersion.v3,
      language: OpenFoodFactsLanguage.ENGLISH,
      fields: [ProductField.ALL],
    );

    try {
      final result = await OpenFoodAPIClient.getProductV3(
        configuration,
      ).timeout(const Duration(seconds: 15));

      if (result.status == ProductResultV3.statusFailure) {
        throw Exception('Open Food Facts could not process the request.');
      }

      // A successful HTTP/API response does not guarantee that
      // the barcode exists in the database.
      return result.product;
    } on FormatException {
      rethrow;
    } on Exception catch (error) {
      throw Exception(
        'Product lookup failed. Check your connection and retry. '
        'Details: $error',
      );
    }
  }
}
