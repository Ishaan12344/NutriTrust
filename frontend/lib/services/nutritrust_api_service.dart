import 'dart:async';
import 'dart:convert';
import 'dart:developer' as developer;

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

import '../models/health_profile.dart';

class NutriTrustApiException implements Exception {
  const NutriTrustApiException(this.message);

  final String message;

  @override
  String toString() => message;
}

class NutriTrustApiService {
  NutriTrustApiService({http.Client? client, String? baseUrl})
    : _client = client ?? http.Client(),
      _baseUrl = _resolveBaseUrl(baseUrl);

  final http.Client _client;
  final String _baseUrl;

  String get baseUrl => _baseUrl;

  static String _resolveBaseUrl(String? configuredUrl) {
    final configured =
        (configuredUrl ??
                const String.fromEnvironment('NUTRITRUST_API_BASE_URL'))
            .trim();
    if (configured.isNotEmpty) {
      return configured.replaceFirst(RegExp(r'/+$'), '');
    }

    if (kIsWeb) {
      final host = Uri.base.host;
      final isLocal = host == 'localhost' || host == '127.0.0.1';
      return isLocal
          ? Uri(scheme: Uri.base.scheme, host: host, port: 8000).toString()
          : Uri.base.origin;
    }

    if (defaultTargetPlatform == TargetPlatform.android) {
      // Physical Android development uses `adb reverse tcp:8000 tcp:8000`.
      // Emulators should pass http://10.0.2.2:8000 via NUTRITRUST_API_BASE_URL.
      return 'http://127.0.0.1:8000';
    }
    return 'http://127.0.0.1:8000';
  }

  Future<Map<String, dynamic>> analyzeLabel({
    required Uint8List imageBytes,
    required String filename,
    required String contentType,
    String? barcode,
    String? username,
  }) async {
    final queryParams = <String, String>{};
    if (barcode != null && barcode.trim().isNotEmpty) {
      queryParams['barcode'] = barcode.trim();
    }
    if (username != null && username.trim().isNotEmpty) {
      queryParams['username'] = username.trim();
    }
    final uri = Uri.parse('$_baseUrl/api/v1/ocr').replace(
      queryParameters: queryParams.isEmpty ? null : queryParams,
    );
    final request = http.MultipartRequest('POST', uri)
      ..files.add(
        http.MultipartFile.fromBytes(
          'file',
          imageBytes,
          filename: filename,
          contentType: contentType == 'image/png'
              ? MediaType('image', 'png')
              : MediaType('image', 'jpeg'),
        ),
      );

    try {
      developer.log(
        'label request start: ${request.method} ${request.url} '
        'file=$filename type=$contentType bytes=${imageBytes.length}',
        name: 'nutritrust.api',
      );
      final response = await http.Response.fromStream(
        await _client.send(request).timeout(const Duration(seconds: 210)),
      );
      developer.log(
        'label response: ${response.statusCode} bytes=${response.bodyBytes.length}',
        name: 'nutritrust.api',
      );
      return _parseAnalysisResponse(response);
    } on TimeoutException catch (error, stackTrace) {
      developer.log('label request timeout', name: 'nutritrust.api', error: error, stackTrace: stackTrace);
      throw const NutriTrustApiException(
        'The analysis request timed out. Please retry.',
      );
    } on http.ClientException catch (error, stackTrace) {
      developer.log('label network failure', name: 'nutritrust.api', error: error, stackTrace: stackTrace);
      throw const NutriTrustApiException(
        'Could not connect to the NutriTrust backend. Check the API address and connection.',
      );
    } catch (error, stackTrace) {
      developer.log('label request failure', name: 'nutritrust.api', error: error, stackTrace: stackTrace);
      rethrow;
    }
  }

  Future<Map<String, dynamic>> analyzeBarcode(String barcode, {String? username}) async {
    final normalizedBarcode = barcode.trim();
    if (!RegExp(r'^\d{6,14}$').hasMatch(normalizedBarcode)) {
      throw const NutriTrustApiException(
        'Enter or scan a barcode containing 6 to 14 digits.',
      );
    }
    final queryParams = <String, String>{};
    if (username != null && username.trim().isNotEmpty) {
      queryParams['username'] = username.trim();
    }
    final uri = Uri.parse(
      '$_baseUrl/api/v1/open-food-facts/${Uri.encodeComponent(normalizedBarcode)}',
    ).replace(
      queryParameters: queryParams.isEmpty ? null : queryParams,
    );

    try {
      developer.log('barcode request start: GET $uri barcode=$normalizedBarcode', name: 'nutritrust.api');
      final response = await _client
          .get(uri)
          .timeout(const Duration(seconds: 20));
      developer.log('barcode response: ${response.statusCode} bytes=${response.bodyBytes.length}', name: 'nutritrust.api');
      final body = _decodeResponse(response);
      if (body['success'] != true || body['data'] is! Map) {
        throw const NutriTrustApiException(
          'The backend response is missing product data. Please retry.',
        );
      }
      // Newer backends return the canonical analysis generated on the server.
      // Keep the adapter below for a rolling upgrade with an older backend.
      if (body['product_analysis'] is Map) {
        return body;
      }
      return _barcodeResponse(body, Map<String, dynamic>.from(body['data'] as Map));
    } on TimeoutException catch (error, stackTrace) {
      developer.log('barcode request timeout', name: 'nutritrust.api', error: error, stackTrace: stackTrace);
      throw const NutriTrustApiException(
        'The product lookup timed out. Please retry.',
      );
    } on http.ClientException catch (error, stackTrace) {
      developer.log('barcode network failure', name: 'nutritrust.api', error: error, stackTrace: stackTrace);
      throw const NutriTrustApiException(
        'Could not connect to the NutriTrust backend. Check the API address and connection.',
      );
    } catch (error, stackTrace) {
      developer.log('barcode request failure', name: 'nutritrust.api', error: error, stackTrace: stackTrace);
      rethrow;
    }
  }

  Map<String, dynamic> _parseAnalysisResponse(http.Response response) {
    final body = _decodeResponse(response);
    if (body['success'] != true || body['product_analysis'] is! Map) {
      throw const NutriTrustApiException(
        'The backend response is missing product analysis data. Please retry.',
      );
    }
    return body;
  }

  Map<String, dynamic> _decodeResponse(http.Response response) {
    Object? decoded;
    try {
      decoded = jsonDecode(response.body);
    } on FormatException {
      throw const NutriTrustApiException(
        'The backend returned an unreadable response. Please retry.',
      );
    }

    if (decoded is! Map) {
      throw const NutriTrustApiException(
        'The backend returned an unexpected response. Please retry.',
      );
    }
    final body = Map<String, dynamic>.from(decoded);
    developer.log('response parsed: success=${body['success']} keys=${body.keys.join(',')}', name: 'nutritrust.api');
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final detail = body['detail'];
      throw NutriTrustApiException(
        detail is String && detail.isNotEmpty
            ? detail
            : 'The analysis request failed (HTTP ${response.statusCode}).',
      );
    }
    return body;
  }

  Map<String, dynamic> _barcodeResponse(
    Map<String, dynamic> body,
    Map<String, dynamic> data,
  ) {
    final nutrition = data['nutrition_per_100g'] is Map
        ? Map<String, dynamic>.from(data['nutrition_per_100g'] as Map)
        : <String, dynamic>{};
    final servingNutrition = data['nutrition_per_serving'] is Map
        ? Map<String, dynamic>.from(data['nutrition_per_serving'] as Map)
        : <String, dynamic>{};
    final product = <String, dynamic>{
      'name': data['product_name'],
      'brands': data['brands'],
      'barcode': data['barcode'],
      'quantity': data['quantity'],
      'image_front_url': data['image_front_url'],
    };
    return {
      ...body,
      'product_analysis': {
        'schema_version': '1.0',
        'product': product,
        'identification': {...product, 'requested_barcode': data['barcode']},
        'ingredients': {
          'text': data['ingredients_text'],
          'items': data['ingredients'] ?? <dynamic>[],
          'source': 'open_food_facts',
        },
        'allergens': {
          'declaration': data['allergens'],
          'open_food_facts_tags': data['allergens_tags'] ?? <dynamic>[],
          'traces_declaration': data['traces'],
          'traces_tags': data['traces_tags'] ?? <dynamic>[],
          'status': data['allergens'] == null ? 'unknown' : 'information_available_review_required',
        },
        'nutrition': {'per_100g': nutrition, 'per_serving': servingNutrition, 'conflicts': []},
        'classification': {
          'nova_group': data['nova_group'],
          'nutriscore_grade': data['nutriscore_grade'],
          'nutriscore': {
            'reported_grade': data['nutriscore_grade'],
            'source': data['nutriscore_grade'] == null ? null : 'open_food_facts',
          'reported_algorithm_version': data['nutriscore_version'],
            'calculated_status': 'not_calculated',
            'algorithm_version': null,
            'note': 'The NutriTrust component score is not an official Nutri-Score calculation.',
          },
          'environmental_score_grade': data['environmental_score_grade'],
          'additives_count': data['additives_count'],
          'additives_tags': data['additives_tags'] ?? <dynamic>[],
        },
        'data_sources': {
          'product_name': 'open_food_facts',
          'brands': 'open_food_facts',
          'barcode': 'open_food_facts',
          'ingredients': 'open_food_facts',
          'nutrition_per_100g': 'open_food_facts',
          'nutrition_per_serving': servingNutrition.isEmpty ? null : 'open_food_facts',
        },
        'open_food_facts': data,
        'health_analysis': {
          'analysis_status': 'insufficient_data',
          'overall_score_status': 'not_calculated',
          'findings': <dynamic>[],
          'warnings': <dynamic>[],
          'needs_review': true,
        },
        'scoring': body['scoring'],
        'warnings': data['found'] == false ? [data['message'] ?? 'Product not found.'] : <dynamic>[],
        'missing_data_warnings': <dynamic>[],
      },
    };
  }

  /// Requests a natural-language summary of a scan from the backend model.
  ///
  /// [response] is the payload returned by [analyzeLabel] or [analyzeBarcode].
  /// The backend looks the health profile up from [username] and returns
  /// `{"success", "status", "summary", ...}`; it never fails because of the
  /// model, so callers should read `summary` and treat an empty value as
  /// "unavailable".
  Future<Map<String, dynamic>> generateSummary({
    required Map<String, dynamic> response,
    String? username,
  }) async {
    final uri = Uri.parse('$_baseUrl/api/v1/summary');
    final payload = <String, dynamic>{
      if (username != null && username.trim().isNotEmpty)
        'username': username.trim(),
      'product_analysis': _summaryAnalysis(response),
    };
    try {
      developer.log('summary request start: POST $uri', name: 'nutritrust.api');
      final result = await _client
          .post(
            uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(payload),
          )
          .timeout(const Duration(seconds: 180));
      final body = _decodeResponse(result);
      developer.log('summary response: status=${body['status']}', name: 'nutritrust.api');
      return body;
    } on TimeoutException {
      throw const NutriTrustApiException(
        'The summary took too long to generate. Please retry.',
      );
    } on http.ClientException {
      throw const NutriTrustApiException(
        'Could not connect to the NutriTrust backend for the summary.',
      );
    }
  }

  /// Builds the analysis the summary endpoint needs, dropping the bulky raw
  /// Open Food Facts payload so the request stays small.
  Map<String, dynamic> _summaryAnalysis(Map<String, dynamic> response) {
    final analysis = response['product_analysis'] is Map
        ? Map<String, dynamic>.from(response['product_analysis'] as Map)
        : <String, dynamic>{};
    final off = analysis['open_food_facts'];
    if (off is Map) {
      analysis['open_food_facts'] = Map<String, dynamic>.from(off)..remove('data');
    }
    return analysis;
  }

  Future<Map<String, dynamic>> register({
    required String username,
    required String password,
    HealthProfile? profile,
  }) async {
    final uri = Uri.parse('$_baseUrl/api/v1/auth/register');
    final payload = {
      'username': username.trim(),
      'password': password,
      ...?profile?.toJson(),
    };
    try {
      final response = await _client
          .post(
            uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(payload),
          )
          .timeout(const Duration(seconds: 15));
      return _decodeResponse(response);
    } on TimeoutException {
      throw const NutriTrustApiException('The registration request timed out. Please retry.');
    } on http.ClientException {
      throw const NutriTrustApiException('Could not connect to the server. Check your connection.');
    }
  }

  Future<Map<String, dynamic>> login({
    required String username,
    required String password,
  }) async {
    final uri = Uri.parse('$_baseUrl/api/v1/auth/login');
    final payload = {
      'username': username.trim(),
      'password': password,
    };
    try {
      final response = await _client
          .post(
            uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(payload),
          )
          .timeout(const Duration(seconds: 15));
      return _decodeResponse(response);
    } on TimeoutException {
      throw const NutriTrustApiException('The login request timed out. Please retry.');
    } on http.ClientException {
      throw const NutriTrustApiException('Could not connect to the server. Check your connection.');
    }
  }

  Future<HealthProfile> getProfile(String username) async {
    final uri = Uri.parse('$_baseUrl/api/v1/user/profile').replace(
      queryParameters: {'username': username.trim()},
    );
    try {
      final response = await _client
          .get(uri)
          .timeout(const Duration(seconds: 15));
      final body = _decodeResponse(response);
      final rawProfile = body['profile'] is Map ? Map<String, dynamic>.from(body['profile'] as Map) : <String, dynamic>{};
      return HealthProfile.fromJson(rawProfile);
    } on TimeoutException {
      throw const NutriTrustApiException('Request timed out fetching profile.');
    } on http.ClientException {
      throw const NutriTrustApiException('Could not connect to the server.');
    }
  }

  Future<HealthProfile> updateProfile(String username, HealthProfile profile) async {
    final uri = Uri.parse('$_baseUrl/api/v1/user/profile');
    final payload = {
      'username': username.trim(),
      ...profile.toJson(),
    };
    try {
      final response = await _client
          .put(
            uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(payload),
          )
          .timeout(const Duration(seconds: 15));
      final body = _decodeResponse(response);
      final rawProfile = body['profile'] is Map ? Map<String, dynamic>.from(body['profile'] as Map) : <String, dynamic>{};
      return HealthProfile.fromJson(rawProfile);
    } on TimeoutException {
      throw const NutriTrustApiException('Request timed out updating profile.');
    } on http.ClientException {
      throw const NutriTrustApiException('Could not connect to the server.');
    }
  }

  void close() => _client.close();
}
