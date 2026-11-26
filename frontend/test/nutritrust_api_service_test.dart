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
        expect(request.body, isNot(contains('name="ingredients_file"')));
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

  test(
    'label analysis sends the ingredients image as a second multipart file',
    () async {
      final client = MockClient((request) async {
        expect(request.url.path, '/api/v1/ocr');
        expect(request.body, contains('name="file"'));
        expect(request.body, contains('name="ingredients_file"'));
        expect(request.body, contains('filename="ingredients.png"'));
        return http.Response(jsonEncode(responseBody), 200);
      });
      final service = NutriTrustApiService(
        client: client,
        baseUrl: 'https://api.example.test',
      );

      await service.analyzeLabel(
        imageBytes: utf8.encode('png-image-bytes'),
        filename: 'nutrition.png',
        contentType: 'image/png',
        ingredientsImageBytes: utf8.encode('png-ingredients-bytes'),
        ingredientsFilename: 'ingredients.png',
        ingredientsContentType: 'image/png',
      );

      service.close();
    },
  );

  test('register sends JSON payload and returns result', () async {
    final client = MockClient((request) async {
      expect(request.method, 'POST');
      expect(request.url.path, '/api/v1/auth/register');
      final body = jsonDecode(request.body) as Map;
      expect(body['username'], 'johndoe');
      expect(body['password'], 'secret');
      return http.Response(jsonEncode({'success': true, 'message': 'User registered successfully'}), 200);
    });
    final service = NutriTrustApiService(client: client, baseUrl: 'https://api.example.test');
    final res = await service.register(username: 'johndoe', password: 'secret');
    expect(res['success'], isTrue);
    service.close();
  });

  test('login sends JSON payload and returns user profile', () async {
    final client = MockClient((request) async {
      expect(request.method, 'POST');
      expect(request.url.path, '/api/v1/auth/login');
      final body = jsonDecode(request.body) as Map;
      expect(body['username'], 'johndoe');
      return http.Response(
        jsonEncode({
          'success': true,
          'user': {
            'username': 'johndoe',
            'profile': {'name': 'John', 'age': 25, 'weight': 70.0, 'gender': 'Male'},
          },
        }),
        200,
      );
    });
    final service = NutriTrustApiService(client: client, baseUrl: 'https://api.example.test');
    final res = await service.login(username: 'johndoe', password: 'secret');
    expect(res['success'], isTrue);
    expect((res['user'] as Map)['username'], 'johndoe');
    service.close();
  });

  test('summary request sends username and strips raw OFF data', () async {
    final client = MockClient((request) async {
      expect(request.method, 'POST');
      expect(request.url.path, '/api/v1/summary');
      final body = jsonDecode(request.body) as Map;
      expect(body['username'], 'johndoe');
      final analysis = body['product_analysis'] as Map;
      expect(analysis['product'], containsPair('name', 'Sample food'));
      // The bulky raw Open Food Facts payload must not be sent back.
      expect((analysis['open_food_facts'] as Map).containsKey('data'), isFalse);
      return http.Response(
        jsonEncode({
          'success': true,
          'status': 'ok',
          'summary': 'A short summary.',
        }),
        200,
      );
    });
    final service = NutriTrustApiService(client: client, baseUrl: 'https://api.example.test');

    final res = await service.generateSummary(
      username: 'johndoe',
      response: {
        'product_analysis': {
          'product': {'name': 'Sample food'},
          'open_food_facts': {'found': true, 'data': {'raw': 'payload'}},
        },
      },
    );

    expect(res['summary'], 'A short summary.');
    service.close();
  });
}
