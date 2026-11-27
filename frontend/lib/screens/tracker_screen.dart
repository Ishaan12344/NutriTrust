import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../models/tracked_item.dart';
import '../services/nutritrust_api_service.dart';
import '../theme/app_theme.dart';

const _nameSuggestions = [
  'Homemade meal',
  'Restaurant dish',
  'Packaged snack',
  'Beverage',
];

/// Inline fallback used after a scan when the product name cannot be read.
Future<String?> showProductNameDialog(
  BuildContext context, {
  required String title,
  required String message,
  String initial = '',
  bool allowSkip = false,
}) {
  return showDialog<String>(
    context: context,
    barrierDismissible: allowSkip,
    builder: (_) => _ProductNameDialog(
      title: title,
      message: message,
      initial: initial,
      allowSkip: allowSkip,
    ),
  );
}

class _ProductNameDialog extends StatefulWidget {
  const _ProductNameDialog({
    required this.title,
    required this.message,
    required this.initial,
    required this.allowSkip,
  });

  final String title;
  final String message;
  final String initial;
  final bool allowSkip;

  @override
  State<_ProductNameDialog> createState() => _ProductNameDialogState();
}

class _ProductNameDialogState extends State<_ProductNameDialog> {
  late final TextEditingController _controller;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.initial);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.title),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(widget.message),
            const SizedBox(height: 16),
            TextField(
              controller: _controller,
              autofocus: true,
              maxLength: 120,
              textCapitalization: TextCapitalization.words,
              decoration: const InputDecoration(
                labelText: 'Product name',
                hintText: 'e.g. Homemade veggie burger',
              ),
              onSubmitted: (value) {
                final name = value.trim();
                if (name.isNotEmpty) Navigator.pop(context, name);
              },
            ),
            const SizedBox(height: 4),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final suggestion in _nameSuggestions)
                  ActionChip(
                    label: Text(suggestion),
                    onPressed: () {
                      _controller.text = suggestion;
                      _controller.selection = TextSelection.collapsed(
                        offset: suggestion.length,
                      );
                    },
                  ),
              ],
            ),
          ],
        ),
      ),
      actions: [
        if (widget.allowSkip)
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Not now'),
          ),
        ValueListenableBuilder<TextEditingValue>(
          valueListenable: _controller,
          builder: (_, value, _) => FilledButton(
            onPressed: value.text.trim().isEmpty
                ? null
                : () => Navigator.pop(context, value.text.trim()),
            child: const Text('Save'),
          ),
        ),
      ],
    );
  }
}

class TrackerScreen extends StatefulWidget {
  const TrackerScreen({super.key, this.username});

  final String? username;

  @override
  State<TrackerScreen> createState() => _TrackerScreenState();
}

class _TrackerScreenState extends State<TrackerScreen> {
  final NutriTrustApiService _api = NutriTrustApiService();
  String _period = 'daily';
  DateTime _anchor = DateTime.now();
  TrackerSnapshot? _snapshot;
  bool _loading = true;
  String? _error;
  int _requestId = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _api.close();
    super.dispose();
  }

  String get _dateParam {
    final month = _anchor.month.toString().padLeft(2, '0');
    final day = _anchor.day.toString().padLeft(2, '0');
    return '${_anchor.year}-$month-$day';
  }

  Future<void> _load() async {
    final requestId = ++_requestId;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final response = await _api.fetchTracker(
        username: widget.username,
        period: _period,
        date: _dateParam,
      );
      if (!mounted || requestId != _requestId) return;
      setState(() {
        _snapshot = TrackerSnapshot.fromJson(response);
        _loading = false;
      });
    } on NutriTrustApiException catch (error) {
      if (!mounted || requestId != _requestId) return;
      setState(() {
        _error = error.message;
        _loading = false;
      });
    } catch (_) {
      if (!mounted || requestId != _requestId) return;
      setState(() {
        _error = 'The tracker could not be loaded. Please retry.';
        _loading = false;
      });
    }
  }

  void _setPeriod(String period) {
    if (period == _period) return;
    setState(() => _period = period);
    _load();
  }

  void _shiftPeriod(int direction) {
    setState(() {
      if (_period == 'daily') {
        _anchor = _anchor.add(Duration(days: direction));
      } else if (_period == 'weekly') {
        _anchor = _anchor.add(Duration(days: direction * 7));
      } else {
        _anchor = DateTime(_anchor.year, _anchor.month + direction, 1);
      }
    });
    _load();
  }

  Future<void> _setStatus(TrackedItem item, ConsumptionStatus status) async {
    try {
      if (status == ConsumptionStatus.notEaten) {
        await _api.deleteTrackerItem(item.id, username: widget.username);
      } else {
        final next = item.status == status ? ConsumptionStatus.pending : status;
        await _api.updateTrackerItem(
          item.id,
          username: widget.username,
          status: next.wire,
        );
      }
      await _load();
    } on NutriTrustApiException catch (error) {
      _showMessage(error.message);
    }
  }

  Future<void> _editName(TrackedItem item) async {
    final name = await showProductNameDialog(
      context,
      title: 'Edit item name',
      message: 'Give this item a name you will recognise later.',
      initial: item.needsName ? '' : item.name,
    );
    if (name == null || !mounted) return;
    try {
      await _api.updateTrackerItem(
        item.id,
        username: widget.username,
        name: name,
      );
      await _load();
    } on NutriTrustApiException catch (error) {
      _showMessage(error.message);
    }
  }

  void _showMessage(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    final snapshot = _snapshot;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Tracker'),
        actions: [
          IconButton(
            tooltip: 'Refresh tracker',
            onPressed: _loading ? null : _load,
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
          children: [
            _buildPeriodSelector(),
            const SizedBox(height: 12),
            _buildDateNavigation(),
            if (_loading && snapshot != null) ...[
              const SizedBox(height: 12),
              const LinearProgressIndicator(minHeight: 2),
            ],
            const SizedBox(height: 16),
            if (_loading && snapshot == null)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 80),
                child: Center(child: CircularProgressIndicator()),
              )
            else if (_error != null && snapshot == null)
              _buildErrorState()
            else if (snapshot != null) ...[
              if (!snapshot.hasData) _buildEmptyState(),
              if (snapshot.hasData) ...[
                _buildHero(snapshot),
                const SizedBox(height: 20),
                _buildMicronutrients(snapshot),
                const SizedBox(height: 20),
                _buildRecommendations(snapshot),
                const SizedBox(height: 20),
                _buildTrend(snapshot),
                const SizedBox(height: 20),
                _buildBreakdown(snapshot),
                const SizedBox(height: 20),
                _buildItems(snapshot),
              ],
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildPeriodSelector() {
    return SegmentedButton<String>(
      segments: const [
        ButtonSegment(value: 'daily', label: Text('Daily')),
        ButtonSegment(value: 'weekly', label: Text('Weekly')),
        ButtonSegment(value: 'monthly', label: Text('Monthly')),
      ],
      selected: {_period},
      showSelectedIcon: false,
      onSelectionChanged: (values) => _setPeriod(values.first),
    );
  }

  Widget _buildDateNavigation() {
    return Row(
      children: [
        IconButton(
          tooltip: 'Previous $_period',
          onPressed: () => _shiftPeriod(-1),
          icon: const Icon(Icons.chevron_left_rounded),
        ),
        Expanded(
          child: Text(
            _snapshot?.rangeLabel ?? _fallbackLabel(),
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.titleMedium,
          ),
        ),
        IconButton(
          tooltip: 'Next $_period',
          onPressed: () => _shiftPeriod(1),
          icon: const Icon(Icons.chevron_right_rounded),
        ),
      ],
    );
  }

  String _fallbackLabel() {
    const months = [
      'Jan',
      'Feb',
      'Mar',
      'Apr',
      'May',
      'Jun',
      'Jul',
      'Aug',
      'Sep',
      'Oct',
      'Nov',
      'Dec',
    ];
    if (_period == 'monthly') {
      return '${months[_anchor.month - 1]} ${_anchor.year}';
    }
    if (_period == 'weekly') {
      final start = _anchor.subtract(Duration(days: _anchor.weekday - 1));
      final end = start.add(const Duration(days: 6));
      return '${start.day}–${end.day} ${months[end.month - 1]}';
    }
    return '${_anchor.day} ${months[_anchor.month - 1]} ${_anchor.year}';
  }

  Widget _buildHero(TrackerSnapshot snapshot) {
    final target = snapshot.calorieTarget;
    final ratio = target > 0
        ? (snapshot.calories / target).clamp(0.0, 1.0)
        : 0.0;
    final percent = snapshot.caloriePercent;
    return Container(
      decoration: BoxDecoration(
        gradient: AppTheme.primaryGradient,
        borderRadius: BorderRadius.circular(24),
      ),
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              SizedBox(
                width: 94,
                height: 94,
                child: Stack(
                  alignment: Alignment.center,
                  children: [
                    SizedBox.expand(
                      child: CircularProgressIndicator(
                        value: ratio,
                        strokeWidth: 9,
                        backgroundColor: Colors.white.withValues(alpha: 0.22),
                        valueColor: const AlwaysStoppedAnimation<Color>(
                          Colors.white,
                        ),
                      ),
                    ),
                    Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          '${percent.round()}%',
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 22,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                        const Text(
                          'of goal',
                          style: TextStyle(color: Colors.white70, fontSize: 11),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Calories',
                      style: TextStyle(color: Colors.white70, fontSize: 13),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '${_format(snapshot.calories)} / ${_format(target)} kcal',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 22,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      snapshot.highlight,
                      style: const TextStyle(
                        color: Colors.white70,
                        fontSize: 12,
                        height: 1.35,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          _TargetBar(
            label: 'Protein',
            value: snapshot.totals['protein'] ?? 0,
            target: snapshot.periodTargets['protein'] ?? 0,
            unit: 'g',
            onGradient: true,
          ),
          _TargetBar(
            label: 'Carbs',
            value: snapshot.totals['total_carbohydrate'] ?? 0,
            target: snapshot.periodTargets['total_carbohydrate'] ?? 0,
            unit: 'g',
            onGradient: true,
          ),
          _TargetBar(
            label: 'Fat',
            value: snapshot.totals['total_fat'] ?? 0,
            target: snapshot.periodTargets['total_fat'] ?? 0,
            unit: 'g',
            onGradient: true,
          ),
          _TargetBar(
            label: 'Fibre',
            value: snapshot.totals['fiber'] ?? 0,
            target: snapshot.periodTargets['fiber'] ?? 0,
            unit: 'g',
            onGradient: true,
          ),
          _TargetBar(
            label: 'Sugar',
            value: snapshot.totals['sugar'] ?? 0,
            target: snapshot.periodTargets['sugar'] ?? 0,
            unit: 'g',
            isLimit: true,
            onGradient: true,
          ),
          _TargetBar(
            label: 'Sodium',
            value: snapshot.totals['sodium'] ?? 0,
            target: snapshot.periodTargets['sodium'] ?? 0,
            unit: 'mg',
            isLimit: true,
            onGradient: true,
          ),
        ],
      ),
    );
  }

  Widget _buildMicronutrients(TrackerSnapshot snapshot) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: scheme.surface,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: scheme.outlineVariant),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Micronutrients',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 2),
          Text(
            'Key minerals from items marked eaten',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: 8),
          _TargetBar(
            label: 'Calcium',
            value: snapshot.totals['calcium'] ?? 0,
            target: snapshot.periodTargets['calcium'] ?? 0,
            unit: 'mg',
          ),
          _TargetBar(
            label: 'Iron',
            value: snapshot.totals['iron'] ?? 0,
            target: snapshot.periodTargets['iron'] ?? 0,
            unit: 'mg',
          ),
          _TargetBar(
            label: 'Potassium',
            value: snapshot.totals['potassium'] ?? 0,
            target: snapshot.periodTargets['potassium'] ?? 0,
            unit: 'mg',
          ),
        ],
      ),
    );
  }

  Widget _buildRecommendations(TrackerSnapshot snapshot) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: scheme.surface,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: scheme.outlineVariant),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.auto_awesome_rounded, color: AppTheme.primaryGreen),
              const SizedBox(width: 8),
              Text(
                'Suggestions for you',
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ],
          ),
          const SizedBox(height: 10),
          for (final recommendation in snapshot.recommendations)
            _RecommendationTile(recommendation: recommendation),
        ],
      ),
    );
  }

  Widget _buildTrend(TrackerSnapshot snapshot) {
    final days = snapshot.trendDays;
    final allZero = days.every((day) => day.calories == 0);
    return _TrendCard(
      title: _period == 'daily' ? 'Last 7 days' : 'Daily calories',
      subtitle: _period == 'daily'
          ? 'A quick look at your recent intake'
          : 'Eaten items only, ${snapshot.rangeLabel}',
      days: days,
      dailyTarget: snapshot.targets['energy_kcal'] ?? 0,
      empty: allZero,
    );
  }

  Widget _buildBreakdown(TrackerSnapshot snapshot) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        _CountChip(
          label: 'Eaten',
          count: snapshot.eatenCount,
          color: AppTheme.trafficGreen,
        ),
        _CountChip(
          label: 'Not eaten',
          count: snapshot.notEatenCount,
          color: Theme.of(context).colorScheme.onSurfaceVariant,
        ),
        _CountChip(
          label: 'Pending',
          count: snapshot.pendingCount,
          color: AppTheme.trafficAmber,
        ),
        if (snapshot.partialDataCount > 0)
          _CountChip(
            label: 'Partial data',
            count: snapshot.partialDataCount,
            color: AppTheme.accentAmber,
          ),
      ],
    );
  }

  Widget _buildItems(TrackerSnapshot snapshot) {
    final items = snapshot.items;
    final groups = <String, List<TrackedItem>>{};
    for (final item in items) {
      groups.putIfAbsent(item.date, () => []).add(item);
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text(
              _period == 'daily' ? "Today's items" : 'Items in this period',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const Spacer(),
            Text(
              '${items.length}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
        const SizedBox(height: 10),
        for (final entry in groups.entries) ...[
          if (_period != 'daily')
            Padding(
              padding: const EdgeInsets.only(top: 4, bottom: 8),
              child: Text(
                _shortDate(entry.key),
                style: Theme.of(context).textTheme.labelMedium,
              ),
            ),
          for (final item in entry.value)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: _ItemCard(
                item: item,
                onStatus: (status) => _setStatus(item, status),
                onEditName: () => _editName(item),
              ),
            ),
        ],
      ],
    );
  }

  Widget _buildEmptyState() {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(28),
      decoration: BoxDecoration(
        color: scheme.surface,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: scheme.outlineVariant),
      ),
      child: Column(
        children: [
          Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              color: AppTheme.primaryGreen.withValues(alpha: 0.1),
              shape: BoxShape.circle,
            ),
            child: const Icon(
              Icons.restaurant_menu_rounded,
              size: 34,
              color: AppTheme.primaryGreen,
            ),
          ),
          const SizedBox(height: 16),
          Text(
            'No items tracked yet',
            style: Theme.of(context).textTheme.titleLarge,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 8),
          Text(
            'Scan a food label or barcode to add it here, then mark what you ate. '
            'Only eaten items count toward your totals.',
            style: Theme.of(context).textTheme.bodyMedium,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 20),
          FilledButton.icon(
            onPressed: () => Navigator.of(context).maybePop(),
            icon: const Icon(Icons.qr_code_scanner_rounded),
            label: const Text('Scan a food item'),
          ),
        ],
      ),
    );
  }

  Widget _buildErrorState() {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 48),
      child: Column(
        children: [
          const Icon(Icons.cloud_off_rounded, size: 40),
          const SizedBox(height: 12),
          Text(
            _error ?? 'The tracker could not be loaded.',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: _load,
            icon: const Icon(Icons.refresh_rounded),
            label: const Text('Retry'),
          ),
        ],
      ),
    );
  }
}

class _TargetBar extends StatelessWidget {
  const _TargetBar({
    required this.label,
    required this.value,
    required this.target,
    required this.unit,
    this.isLimit = false,
    this.onGradient = false,
  });

  final String label;
  final double value;
  final double target;
  final String unit;
  final bool isLimit;
  final bool onGradient;

  @override
  Widget build(BuildContext context) {
    final percent = target > 0 ? value / target * 100 : 0.0;
    final scheme = Theme.of(context).colorScheme;
    final Color color;
    if (isLimit) {
      if (percent >= 100) {
        color = onGradient ? const Color(0xFFFFB4A2) : AppTheme.trafficRed;
      } else if (percent >= 80) {
        color = onGradient ? const Color(0xFFFFD180) : AppTheme.trafficAmber;
      } else {
        color = onGradient ? Colors.white : AppTheme.trafficGreen;
      }
    } else if (percent >= 70) {
      color = onGradient ? const Color(0xFFB9F6CA) : AppTheme.trafficGreen;
    } else if (percent >= 40) {
      color = onGradient ? const Color(0xFFFFE082) : AppTheme.trafficAmber;
    } else {
      color = onGradient ? const Color(0xFFFFB4A2) : AppTheme.trafficRed;
    }
    final labelColor = onGradient ? Colors.white70 : scheme.onSurfaceVariant;
    final valueColor = onGradient ? Colors.white : scheme.onSurface;
    return Semantics(
      label: '$label ${_format(value)} of ${_format(target)} $unit',
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 5),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    label,
                    style: TextStyle(fontSize: 13, color: labelColor),
                  ),
                ),
                Text(
                  '${_format(value)} / ${_format(target)} $unit',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: valueColor,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 4),
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                value: (percent / 100).clamp(0.0, 1.0),
                minHeight: 6,
                backgroundColor: onGradient
                    ? Colors.white24
                    : scheme.surfaceContainerHighest,
                valueColor: AlwaysStoppedAnimation<Color>(color),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _RecommendationTile extends StatelessWidget {
  const _RecommendationTile({required this.recommendation});

  final TrackerRecommendation recommendation;

  @override
  Widget build(BuildContext context) {
    final (icon, color) = switch (recommendation.type) {
      'eat' => (Icons.restaurant_rounded, AppTheme.primaryGreen),
      'avoid' => (Icons.warning_amber_rounded, AppTheme.errorColor),
      'good' => (Icons.check_circle_rounded, AppTheme.trafficGreen),
      _ => (Icons.info_outline_rounded, AppTheme.accentAmber),
    };
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(icon, size: 18, color: color),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  recommendation.title,
                  style: Theme.of(
                    context,
                  ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
                ),
                const SizedBox(height: 2),
                Text(
                  recommendation.message,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _CountChip extends StatelessWidget {
  const _CountChip({
    required this.label,
    required this.count,
    required this.color,
  });

  final String label;
  final int count;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: '$count $label items',
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Text(
          '$count $label',
          style: TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w600,
            color: color,
          ),
        ),
      ),
    );
  }
}

class _ItemCard extends StatelessWidget {
  const _ItemCard({
    required this.item,
    required this.onStatus,
    required this.onEditName,
  });

  final TrackedItem item;
  final ValueChanged<ConsumptionStatus> onStatus;
  final VoidCallback onEditName;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final statusColor = switch (item.status) {
      ConsumptionStatus.eaten => AppTheme.trafficGreen,
      ConsumptionStatus.notEaten => scheme.onSurfaceVariant,
      ConsumptionStatus.pending => AppTheme.trafficAmber,
    };
    final statusIcon = switch (item.status) {
      ConsumptionStatus.eaten => Icons.check_rounded,
      ConsumptionStatus.notEaten => Icons.remove_rounded,
      ConsumptionStatus.pending => Icons.schedule_rounded,
    };
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: scheme.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: item.status == ConsumptionStatus.pending
              ? AppTheme.trafficAmber.withValues(alpha: 0.45)
              : scheme.outlineVariant,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                margin: const EdgeInsets.only(top: 2),
                padding: const EdgeInsets.all(7),
                decoration: BoxDecoration(
                  color: statusColor.withValues(alpha: 0.12),
                  shape: BoxShape.circle,
                ),
                child: Icon(statusIcon, size: 18, color: statusColor),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      item.name,
                      style: Theme.of(context).textTheme.titleSmall?.copyWith(
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    if (item.brand != null && item.brand!.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 2),
                        child: Text(
                          item.brand!,
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ),
                    const SizedBox(height: 6),
                    Wrap(
                      spacing: 6,
                      runSpacing: 4,
                      children: [
                        if (item.manualName)
                          _Tag(
                            label: 'Added by you',
                            color: AppTheme.primaryGreen,
                          ),
                        if (item.needsName)
                          _Tag(
                            label: 'Name needed',
                            color: AppTheme.trafficAmber,
                          ),
                        if (item.partialData)
                          _Tag(
                            label: 'Partial data',
                            color: AppTheme.accentAmber,
                          ),
                        if (item.allergens.isNotEmpty)
                          _Tag(
                            label: 'Allergens listed',
                            color: AppTheme.errorColor,
                          ),
                        if (item.nutriGrade != null &&
                            item.nutriGrade!.isNotEmpty &&
                            item.nutriGrade!.toLowerCase() != 'n/a')
                          _Tag(
                            label:
                                'Nutri-Score ${item.nutriGrade!.toUpperCase()}',
                            color: AppTheme.gradeColor(item.nutriGrade),
                          ),
                      ],
                    ),
                  ],
                ),
              ),
              IconButton(
                tooltip: 'Edit item name',
                onPressed: onEditName,
                icon: const Icon(Icons.edit_rounded, size: 18),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 10,
            runSpacing: 4,
            children: [
              _Macro(label: '${_format(item.calories)} kcal'),
              _Macro(label: 'P ${_format(item.protein)} g'),
              _Macro(label: 'C ${_format(item.carbs)} g'),
              _Macro(label: 'F ${_format(item.fat)} g'),
              if (item.sugar > 0)
                _Macro(label: 'Sugar ${_format(item.sugar)} g'),
              if (item.sodium > 0)
                _Macro(label: 'Sodium ${_format(item.sodium)} mg'),
            ],
          ),
          if (item.nutritionBasis == 'per_100g')
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                'Values per 100 g',
                style: Theme.of(context).textTheme.labelSmall,
              ),
            ),
          if (item.allergens.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(
                'Allergens: ${item.allergens.join(', ')}',
                style: const TextStyle(
                  fontSize: 11,
                  color: AppTheme.errorColor,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
          if (item.additives.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 3),
              child: Text(
                'Additives listed: ${item.additives.length}',
                style: Theme.of(context).textTheme.labelSmall,
              ),
            ),
          const SizedBox(height: 10),
          Row(
            children: [
              if (item.status == ConsumptionStatus.eaten &&
                  item.consumedAt != null)
                Expanded(
                  child: Text(
                    'Eaten at ${_time(item.consumedAt!)}',
                    style: TextStyle(
                      fontSize: 12,
                      color: statusColor,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                )
              else if (item.status == ConsumptionStatus.pending)
                const Expanded(
                  child: Text(
                    'Tap Eaten when you have it',
                    style: TextStyle(
                      fontSize: 12,
                      color: AppTheme.trafficAmber,
                    ),
                  ),
                )
              else
                const Spacer(),
              _StatusButton(
                label: 'Eaten',
                icon: Icons.check_rounded,
                selected: item.status == ConsumptionStatus.eaten,
                color: AppTheme.trafficGreen,
                semanticsLabel: 'Mark ${item.name} as eaten',
                onTap: () => onStatus(ConsumptionStatus.eaten),
              ),
              const SizedBox(width: 8),
              _StatusButton(
                label: 'Not eaten',
                icon: Icons.remove_rounded,
                selected: item.status == ConsumptionStatus.notEaten,
                color: scheme.onSurfaceVariant,
                semanticsLabel: 'Mark ${item.name} as not eaten',
                onTap: () => onStatus(ConsumptionStatus.notEaten),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _StatusButton extends StatelessWidget {
  const _StatusButton({
    required this.label,
    required this.icon,
    required this.selected,
    required this.color,
    required this.semanticsLabel,
    required this.onTap,
  });

  final String label;
  final IconData icon;
  final bool selected;
  final Color color;
  final String semanticsLabel;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Semantics(
      button: true,
      selected: selected,
      label: semanticsLabel,
      child: Material(
        color: selected
            ? color.withValues(alpha: 0.14)
            : scheme.surfaceContainer,
        borderRadius: BorderRadius.circular(12),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(12),
          child: Container(
            height: 48,
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  icon,
                  size: 17,
                  color: selected ? color : scheme.onSurfaceVariant,
                ),
                const SizedBox(width: 5),
                Text(
                  label,
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: selected ? color : scheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Tag extends StatelessWidget {
  const _Tag({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.w600,
          color: color,
        ),
      ),
    );
  }
}

class _Macro extends StatelessWidget {
  const _Macro({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Text(
      label,
      style: TextStyle(
        fontSize: 11,
        color: Theme.of(context).colorScheme.onSurfaceVariant,
      ),
    );
  }
}

class _TrendCard extends StatelessWidget {
  const _TrendCard({
    required this.title,
    required this.subtitle,
    required this.days,
    required this.dailyTarget,
    required this.empty,
  });

  final String title;
  final String subtitle;
  final List<TrackerDay> days;
  final double dailyTarget;
  final bool empty;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: scheme.surface,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: scheme.outlineVariant),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 2),
          Text(subtitle, style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: 14),
          if (empty)
            SizedBox(
              height: 120,
              child: Center(
                child: Text(
                  'No eaten items in this period yet.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ),
            )
          else
            SizedBox(
              height: 150,
              child: CustomPaint(
                size: Size.infinite,
                painter: _TrendPainter(
                  days: days,
                  dailyTarget: dailyTarget,
                  barColor: AppTheme.primaryGreen,
                  targetColor: AppTheme.trafficAmber,
                  gridColor: scheme.outlineVariant,
                  textColor: scheme.onSurfaceVariant,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _TrendPainter extends CustomPainter {
  _TrendPainter({
    required this.days,
    required this.dailyTarget,
    required this.barColor,
    required this.targetColor,
    required this.gridColor,
    required this.textColor,
  });

  final List<TrackerDay> days;
  final double dailyTarget;
  final Color barColor;
  final Color targetColor;
  final Color gridColor;
  final Color textColor;

  @override
  void paint(Canvas canvas, Size size) {
    if (days.isEmpty) return;
    const labelHeight = 18.0;
    final plotHeight = size.height - labelHeight;
    final maxValue = math.max(
      1.0,
      days
          .map((day) => day.calories)
          .fold<double>(0.0, (current, value) => math.max(current, value)),
    );
    final scaleMax = math.max(maxValue, dailyTarget) * 1.1;
    final slot = size.width / days.length;

    final gridPaint = Paint()
      ..color = gridColor
      ..strokeWidth = 1;
    canvas.drawLine(
      Offset(0, plotHeight),
      Offset(size.width, plotHeight),
      gridPaint,
    );

    if (dailyTarget > 0) {
      final y = plotHeight - (dailyTarget / scaleMax) * plotHeight;
      final dashPaint = Paint()
        ..color = targetColor.withValues(alpha: 0.6)
        ..strokeWidth = 1;
      for (double x = 0; x < size.width; x += 8) {
        canvas.drawLine(Offset(x, y), Offset(x + 4, y), dashPaint);
      }
    }

    final barPaint = Paint()..color = barColor;
    final labelEvery = days.length > 12 ? 5 : 1;
    for (var index = 0; index < days.length; index++) {
      final day = days[index];
      final height = (day.calories / scaleMax) * plotHeight;
      final width = math.min(26.0, slot * 0.55);
      final left = slot * index + (slot - width) / 2;
      final rect = RRect.fromRectAndRadius(
        Rect.fromLTWH(left, plotHeight - height, width, height),
        const Radius.circular(4),
      );
      if (day.calories > 0) {
        canvas.drawRRect(rect, barPaint);
      } else {
        canvas.drawRRect(
          rect,
          Paint()..color = gridColor.withValues(alpha: 0.5),
        );
      }

      if (index % labelEvery == 0 || index == days.length - 1) {
        final date = DateTime.tryParse(day.date);
        if (date == null) continue;
        final painter = TextPainter(
          text: TextSpan(
            text: '${date.day}',
            style: TextStyle(fontSize: 10, color: textColor),
          ),
          textDirection: TextDirection.ltr,
        )..layout();
        painter.paint(
          canvas,
          Offset(left + width / 2 - painter.width / 2, plotHeight + 4),
        );
      }
    }
  }

  @override
  bool shouldRepaint(_TrendPainter oldDelegate) =>
      oldDelegate.days != days || oldDelegate.dailyTarget != dailyTarget;
}

String _format(double value) {
  if (value >= 100) return value.round().toString();
  if (value % 1 == 0) return value.toInt().toString();
  return value.toStringAsFixed(1);
}

String _time(DateTime time) {
  final hour = time.hour % 12 == 0 ? 12 : time.hour % 12;
  final minute = time.minute.toString().padLeft(2, '0');
  return '$hour:$minute ${time.hour < 12 ? 'AM' : 'PM'}';
}

String _shortDate(String isoDate) {
  const months = [
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec',
  ];
  const weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  final date = DateTime.tryParse(isoDate);
  if (date == null) return isoDate;
  return '${weekdays[date.weekday - 1]}, ${date.day} ${months[date.month - 1]}';
}
