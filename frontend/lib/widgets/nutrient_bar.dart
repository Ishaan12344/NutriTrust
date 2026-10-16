import 'package:flutter/material.dart';

class NutrientBar extends StatelessWidget {
  const NutrientBar({
    super.key,
    required this.label,
    required this.servingValue,
    required this.per100Value,
    this.dvPercent,
    this.isLimitNutrient = true,
  });

  final String label;
  final String servingValue;
  final String per100Value;
  final num? dvPercent;
  final bool isLimitNutrient;

  Color _barColor(double percent) {
    if (isLimitNutrient) {
      if (percent <= 5) return const Color(0xFF229954);
      if (percent <= 20) return const Color(0xFF85BB2F);
      if (percent <= 40) return const Color(0xFFF39C12);
      return const Color(0xFFE74C3C);
    }
    if (percent >= 20) return const Color(0xFF229954);
    if (percent >= 10) return const Color(0xFFF39C12);
    return const Color(0xFFE74C3C);
  }

  @override
  Widget build(BuildContext context) {
    if (servingValue.isEmpty && per100Value.isEmpty) {
      return const SizedBox.shrink();
    }

    final dv = dvPercent?.toDouble() ?? 0;
    final barProgress = (dv / 100).clamp(0.0, 1.0);
    final color = _barColor(dv);

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  label,
                  style: const TextStyle(
                      fontSize: 14, fontWeight: FontWeight.w500),
                ),
              ),
              if (servingValue.isNotEmpty)
                Text(
                  servingValue,
                  style: TextStyle(
                    fontSize: 13,
                    color: Colors.grey.shade700,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              if (dvPercent != null) ...[
                const SizedBox(width: 8),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: color.withOpacity(0.12),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    '${dvPercent!.round()}%',
                    style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                        color: color),
                  ),
                ),
              ],
            ],
          ),
          if (dvPercent != null) ...[
            const SizedBox(height: 4),
            TweenAnimationBuilder<double>(
              tween: Tween(begin: 0, end: barProgress),
              duration: const Duration(milliseconds: 800),
              curve: Curves.easeOutCubic,
              builder: (_, value, __) => ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: LinearProgressIndicator(
                  value: value,
                  backgroundColor: Colors.grey.shade200,
                  valueColor: AlwaysStoppedAnimation(color),
                  minHeight: 6,
                ),
              ),
            ),
          ],
          if (per100Value.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text(
                'Per 100 g: $per100Value',
                style: TextStyle(fontSize: 11, color: Colors.grey.shade500),
              ),
            ),
        ],
      ),
    );
  }
}
