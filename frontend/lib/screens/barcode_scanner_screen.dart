import 'dart:developer' as developer;

import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../theme/app_theme.dart';

class BarcodeScannerScreen extends StatefulWidget {
  const BarcodeScannerScreen({super.key});

  @override
  State<BarcodeScannerScreen> createState() => _BarcodeScannerScreenState();
}

class _BarcodeScannerScreenState extends State<BarcodeScannerScreen>
    with SingleTickerProviderStateMixin {
  bool _hasScanned = false;
  late final AnimationController _scanLineController;

  @override
  void initState() {
    super.initState();
    _scanLineController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _scanLineController.dispose();
    super.dispose();
  }

  void _onDetect(BarcodeCapture capture) {
    developer.log(
        'scanner detection callback: ${capture.barcodes.length} candidates',
        name: 'nutritrust.scanner');
    if (_hasScanned) return;

    for (final barcode in capture.barcodes) {
      final value = barcode.rawValue?.trim();
      if (value != null && value.isNotEmpty) {
        developer.log('scanner decoded a barcode', name: 'nutritrust.scanner');
        _hasScanned = true;
        Navigator.of(context).pop(value);
        return;
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.of(context).size;
    final scanAreaSize = size.width * 0.72;

    return Scaffold(
      backgroundColor: Colors.black,
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        foregroundColor: Colors.white,
        title: const Text('Scan Barcode',
            style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
        leading: IconButton(
          icon: Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: Colors.black.withValues(alpha: 0.4),
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Icon(Icons.arrow_back_rounded, color: Colors.white),
          ),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: Stack(
        children: [
          MobileScanner(onDetect: _onDetect),
          CustomPaint(
            size: size,
            painter: _ScanOverlayPainter(
              scanAreaSize: scanAreaSize,
              borderRadius: 20,
            ),
          ),
          Center(
            child: SizedBox(
              width: scanAreaSize,
              height: scanAreaSize,
              child: Stack(
                children: [
                  ..._cornerBrackets(scanAreaSize),
                  AnimatedBuilder(
                    animation: _scanLineController,
                    builder: (_, _) => Positioned(
                      top: _scanLineController.value * (scanAreaSize - 4),
                      left: 16,
                      right: 16,
                      child: Container(
                        height: 3,
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(2),
                          gradient: LinearGradient(
                            colors: [
                              AppTheme.accentTeal.withValues(alpha: 0),
                              AppTheme.accentTeal,
                              AppTheme.primaryGreen,
                              AppTheme.accentTeal,
                              AppTheme.accentTeal.withValues(alpha: 0),
                            ],
                          ),
                          boxShadow: [
                            BoxShadow(
                              color: AppTheme.accentTeal.withValues(alpha: 0.6),
                              blurRadius: 12,
                              spreadRadius: 2,
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          Positioned(
            bottom: 80,
            left: 40,
            right: 40,
            child: Column(
              children: [
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                  decoration: BoxDecoration(
                    color: Colors.black.withValues(alpha: 0.6),
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: const Text(
                    'Align the barcode within the frame',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 15,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  'It will be scanned automatically',
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.6),
                    fontSize: 13,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  List<Widget> _cornerBrackets(double size) {
    const len = 32.0;
    const thick = 3.5;
    const color = AppTheme.accentTeal;

    Widget corner({
      required Alignment alignment,
      required BorderRadius borderRadius,
    }) {
      return Align(
        alignment: alignment,
        child: Container(
          width: len,
          height: len,
          decoration: BoxDecoration(
            borderRadius: borderRadius,
            border: Border(
              top: alignment.y < 0
                  ? const BorderSide(color: color, width: thick)
                  : BorderSide.none,
              bottom: alignment.y > 0
                  ? const BorderSide(color: color, width: thick)
                  : BorderSide.none,
              left: alignment.x < 0
                  ? const BorderSide(color: color, width: thick)
                  : BorderSide.none,
              right: alignment.x > 0
                  ? const BorderSide(color: color, width: thick)
                  : BorderSide.none,
            ),
          ),
        ),
      );
    }

    return [
      corner(
          alignment: Alignment.topLeft,
          borderRadius:
              const BorderRadius.only(topLeft: Radius.circular(20))),
      corner(
          alignment: Alignment.topRight,
          borderRadius:
              const BorderRadius.only(topRight: Radius.circular(20))),
      corner(
          alignment: Alignment.bottomLeft,
          borderRadius:
              const BorderRadius.only(bottomLeft: Radius.circular(20))),
      corner(
          alignment: Alignment.bottomRight,
          borderRadius:
              const BorderRadius.only(bottomRight: Radius.circular(20))),
    ];
  }
}

class _ScanOverlayPainter extends CustomPainter {
  _ScanOverlayPainter({required this.scanAreaSize, this.borderRadius = 20});

  final double scanAreaSize;
  final double borderRadius;

  @override
  void paint(Canvas canvas, Size size) {
    final bg = Paint()..color = Colors.black.withValues(alpha: 0.55);
    final center = Offset(size.width / 2, size.height / 2);
    final cutout = RRect.fromRectAndRadius(
      Rect.fromCenter(
          center: center, width: scanAreaSize, height: scanAreaSize),
      Radius.circular(borderRadius),
    );

    final path = Path()
      ..addRect(Rect.fromLTWH(0, 0, size.width, size.height))
      ..addRRect(cutout)
      ..fillType = PathFillType.evenOdd;

    canvas.drawPath(path, bg);
  }

  @override
  bool shouldRepaint(_ScanOverlayPainter old) =>
      old.scanAreaSize != scanAreaSize;
}
