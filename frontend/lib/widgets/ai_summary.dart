import 'package:flutter/material.dart';

import '../services/nutritrust_api_service.dart';
import '../theme/app_theme.dart';

/// Renders the backend's local-model summary for the current analysis.
///
/// The summary is generated on demand so the scan results appear immediately.
/// The backend is best-effort, so this card degrades to a short note instead of
/// an error when the model is disabled, unavailable, or too slow.
class AiSummaryCard extends StatefulWidget {
  const AiSummaryCard({
    super.key,
    required this.api,
    required this.response,
    this.username,
  });

  final NutriTrustApiService api;
  final Map<String, dynamic> response;
  final String? username;

  @override
  State<AiSummaryCard> createState() => _AiSummaryCardState();
}

class _AiSummaryCardState extends State<AiSummaryCard> {
  String? _summary;
  String? _note;
  bool _loading = true;
  int _requestId = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(AiSummaryCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    // A retry can rebuild this card with a new analysis while it stays mounted,
    // so reload whenever the response changes instead of showing a stale summary.
    if (!identical(oldWidget.response, widget.response)) {
      _load();
    }
  }

  Future<void> _load() async {
    final requestId = ++_requestId;
    setState(() {
      _loading = true;
      _summary = null;
      _note = null;
    });
    try {
      final body = await widget.api.generateSummary(
        response: widget.response,
        username: widget.username,
      );
      if (!mounted || requestId != _requestId) return;
      final summary = body['summary']?.toString().trim();
      setState(() {
        if (summary == null || summary.isEmpty) {
          _summary = null;
          _note = _reasonFor(body['status']);
        } else {
          _summary = summary;
          _note = null;
        }
        _loading = false;
      });
    } on NutriTrustApiException catch (error) {
      if (mounted && requestId == _requestId) {
        setState(() {
          _note = error.message;
          _loading = false;
        });
      }
    } catch (_) {
      if (mounted && requestId == _requestId) {
        setState(() {
          _note = 'The summary could not be generated.';
          _loading = false;
        });
      }
    }
  }

  String _reasonFor(Object? status) {
    switch (status) {
      case 'disabled':
        return 'AI summaries are turned off on this server.';
      case 'timeout':
        return 'The summary took too long to generate.';
      case 'insufficient_data':
        return 'There is not enough product data to summarise.';
      default:
        return 'The summary is unavailable right now.';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            AppTheme.accentTeal.withOpacity(0.08),
            AppTheme.primaryGreen.withOpacity(0.06),
          ],
        ),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: AppTheme.accentTeal.withOpacity(0.18)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: AppTheme.accentTeal.withOpacity(0.14),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Icon(Icons.auto_awesome_outlined,
                    color: AppTheme.primaryGreen, size: 20),
              ),
              const SizedBox(width: 10),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('AI Summary',
                        style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w700,
                            color: AppTheme.textDark)),
                    Text('From your profile and this product',
                        style: TextStyle(
                            fontSize: 12, color: AppTheme.textLight)),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          if (_loading)
            Row(
              children: [
                const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
                const SizedBox(width: 10),
                Text(
                  'Generating summary\u2026 this can take a few seconds.',
                  style: TextStyle(
                      fontSize: 13,
                      height: 1.4,
                      color: Colors.grey.shade600),
                ),
              ],
            )
          else if (_summary != null)
            Text(
              _summary!,
              style: const TextStyle(
                  fontSize: 13.5, height: 1.5, color: AppTheme.textDark),
            )
          else
            Text(
              _note ?? 'The summary is unavailable right now.',
              style: TextStyle(
                  fontSize: 13, height: 1.4, color: Colors.grey.shade600),
            ),
          const SizedBox(height: 10),
          Text(
            'Generated by a local model from your saved profile and this '
            'product\u2019s data. Informational only, not medical advice.',
            style: TextStyle(
                fontSize: 11,
                fontStyle: FontStyle.italic,
                color: Colors.grey.shade500),
          ),
        ],
      ),
    );
  }
}
