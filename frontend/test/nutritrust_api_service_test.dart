import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:frontend/services/nutritrust_api_service.dart';

void main() {
  const responseBody = {
    'success': true,
    'product_analysis': {
      'product': {'name': 'Sample food'},
      'health_analysis': {'findings': []},
    },
  };

  test(
    'barcode lookup uses the backend route and decodes product analysis',
    () async {
      final client = MockClient((request) async {
        expect(request.method, 'GET');
        expect(
          request.url.toString(),
          'https://api.example.test/api/v1/open-food-facts/0012345678905',
        );
        return http.Response(jsonEncode(responseBody), 200);
      });
      final service = NutriTrustApiService(
        client: client,
        baseUrl: 'https://api.example.test/',
      );

      final response = await service.analyzeBarcode('0012345678905');

      expect(
        (response['product_analysis'] as Map)['product'],
        containsPair('name', 'Sample food'),
      );
      service.close();
    },
  );

  test(
    'label analysis sends image as multipart file with optional barcode',
    () async {
      final client = MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/api/v1/ocr');
        expect(request.url.queryParameters['barcode'], '0012345678905');
        expect(
          request.headers['content-type'],
          startsWith('multipart/form-data;'),
        );
        expect(request.body, contains('name="file"'));
        expect(request.body, contains('filename="nutrition.png"'));
        return http.Response(jsonEncode(responseBody), 200);
      });
      final service = NutriTrustApiService(
        client: client,
        baseUrl: 'https://api.example.test',
      );

      final response = await service.analyzeLabel(
        imageBytes: utf8.encode('png-image-bytes'),
        filename: 'nutrition.png',
        contentType: 'image/png',
        barcode: '0012345678905',
      );

      expect(response['success'], isTrue);
      service.close();
    },
  );
}
