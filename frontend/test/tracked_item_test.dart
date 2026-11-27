import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/models/tracked_item.dart';

void main() {
  test('parses a tracker snapshot and its consumption statuses', () {
    final snapshot = TrackerSnapshot.fromJson({
      'period': 'weekly',
      'range': {'label': '23–29 Nov 2026'},
      'items': [
        {
          'item_id': 'a1',
          'name': 'Oats',
          'local_date': '2026-11-27',
          'status': 'eaten',
          'manual_name': true,
          'partial_data': true,
          'consumed_at': '2026-11-27T08:30:00+00:00',
          'nutrition': {'energy_kcal': 300, 'protein': 10},
          'allergens': ['milk'],
        },
        {
          'item_id': 'a2',
          'name': 'Chips',
          'local_date': '2026-11-27',
          'status': 'not_eaten',
          'nutrition': {'energy_kcal': 500},
        },
      ],
      'totals': {'energy_kcal': 300, 'protein': 10},
      'targets': {'energy_kcal': 2000, 'protein': 50},
      'period_targets': {'energy_kcal': 14000, 'protein': 350},
      'percentages': {'energy_kcal': 2.1, 'protein': 2.9},
      'days': [
        {
          'date': '2026-11-27',
          'totals': {'energy_kcal': 300},
          'counts': {'eaten': 1, 'not_eaten': 1, 'pending': 0},
        },
      ],
      'trend_days': [
        {
          'date': '2026-11-26',
          'totals': {'energy_kcal': 0},
        },
        {
          'date': '2026-11-27',
          'totals': {'energy_kcal': 300},
        },
      ],
      'counts': {'eaten': 1, 'not_eaten': 1, 'pending': 0},
      'partial_data_count': 1,
      'highlight': 'You hit 3% of your protein goal this week.',
      'has_data': true,
      'targets_available': true,
      'target_note': 'Adult estimate.',
      'nutrient_report_counts': {'added_sugar': 1},
      'recommendations': [
        {
          'type': 'eat',
          'title': 'Add a fibre source',
          'message': 'A fruit would help.',
        },
      ],
    });

    expect(snapshot.period, 'weekly');
    expect(snapshot.items, hasLength(2));
    expect(snapshot.items.first.status, ConsumptionStatus.eaten);
    expect(snapshot.items.first.manualName, isTrue);
    expect(snapshot.items.first.partialData, isTrue);
    expect(snapshot.items.first.consumedAt, isNotNull);
    expect(snapshot.items.last.status, ConsumptionStatus.notEaten);
    expect(snapshot.trendDays, hasLength(2));
    expect(snapshot.recommendations.single.type, 'eat');
    expect(snapshot.eatenCount, 1);
    expect(snapshot.hasData, isTrue);
    expect(snapshot.targetsAvailable, isTrue);
    expect(snapshot.targetNote, 'Adult estimate.');
    expect(snapshot.nutrientReportCounts['added_sugar'], 1);
  });

  test('parses snapshots without applicable adult targets', () {
    final snapshot = TrackerSnapshot.fromJson({
      'targets_available': false,
      'target_note': 'Adult targets are unavailable.',
      'targets': {},
      'period_targets': {},
    });

    expect(snapshot.targetsAvailable, isFalse);
    expect(snapshot.calorieTarget, isNull);
    expect(snapshot.targetNote, 'Adult targets are unavailable.');
  });

  test('unknown status falls back to pending', () {
    expect(ConsumptionStatus.fromWire('later'), ConsumptionStatus.pending);
    expect(ConsumptionStatus.eaten.wire, 'eaten');
    expect(ConsumptionStatus.notEaten.wire, 'not_eaten');
  });
}
