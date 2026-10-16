import 'dart:math';

import 'package:flutter/material.dart';

class ScoreRing extends StatelessWidget {
  const ScoreRing({
    super.key,
    required this.score,
    this.maxScore = 100,
    this.size = 120,
    this.strokeWidth = 10,
    this.color,
    this.label,
    this.grade,
  });

  final num score;
  final num maxScore;
  final double size;
  final double strokeWidth;
  final Color? color;
  final String? label;
  final String? grade;

  Color _colorForProgress(double p) {
    if (p >= 0.8) return const Color(0xFF038141);
    if (p >= 0.6) return const Color(0xFF85BB2F);
    if (p >= 0.4) return const Color(0xFFFECB02);
    if (p >= 0.2) return const Color(0xFFEE8100);
    return const Color(0xFFE63E11);
  }

  @override
  Widget build(BuildContext context) {
    final progress = (score / maxScore).clamp(0.0, 1.0).toDouble();
    final ringColor = color ?? _colorForProgress(progress);

    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: progress),
      duration: const Duration(milliseconds: 1200),
      curve: Curves.easeOutCubic,
      builder: (context, value, _) => SizedBox(
        width: size,
        height: size,
        child: Stack(
          alignment: Alignment.center,
          children: [
            CustomPaint(
              size: Size(size, size),
              painter: _RingPainter(
                progress: value,
                color: ringColor,
                strokeWidth: strokeWidth,
                bgColor: Colors.grey.shade200,
              ),
            ),
            Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  '${(value * maxScore).round()}',
                  style: TextStyle(
                    fontSize: size * 0.26,
                    fontWeight: FontWeight.w800,
                    color: ringColor,
                    height: 1,
                  ),
                ),
                if (grade != null)
                  Text(
                    grade!,
                    style: TextStyle(
                      fontSize: size * 0.11,
                      fontWeight: FontWeight.w600,
                      color: ringColor,
                    ),
                  ),
                if (label != null)
                  Text(
                    label!,
                    style: TextStyle(
                      fontSize: size * 0.08,
                      fontWeight: FontWeight.w500,
                      color: Colors.grey.shade600,
                    ),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _RingPainter extends CustomPainter {
  _RingPainter({
    required this.progress,
    required this.color,
    required this.strokeWidth,
    required this.bgColor,
  });

  final double progress;
  final Color color;
  final double strokeWidth;
  final Color bgColor;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = (size.width - strokeWidth) / 2;

    final bg = Paint()
      ..color = bgColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..strokeCap = StrokeCap.round;
    canvas.drawCircle(center, radius, bg);

    if (progress > 0) {
      final fg = Paint()
        ..color = color
        ..style = PaintingStyle.stroke
        ..strokeWidth = strokeWidth
        ..strokeCap = StrokeCap.round;
      canvas.drawArc(
        Rect.fromCircle(center: center, radius: radius),
        -pi / 2,
        2 * pi * progress,
        false,
        fg,
      );
    }
  }

  @override
  bool shouldRepaint(_RingPainter old) =>
      old.progress != progress || old.color != color;
}
