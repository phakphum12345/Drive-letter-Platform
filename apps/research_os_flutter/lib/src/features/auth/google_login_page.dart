import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../api/research_os_api_client.dart';

class GoogleLoginPage extends StatefulWidget {
  const GoogleLoginPage({required this.apiClient, super.key});

  final ResearchOSApiClient apiClient;

  @override
  State<GoogleLoginPage> createState() => _GoogleLoginPageState();
}

class _GoogleLoginPageState extends State<GoogleLoginPage> {
  bool _busy = false;
  String? _message;
  bool _error = false;

  Future<void> _continueWithGoogle() async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _message = null;
      _error = false;
    });

    try {
      final response = await widget.apiClient.startGoogleIdentitySignIn();
      final state = response['state']?.toString().trim() ?? '';
      if (state.isEmpty) {
        throw const ResearchOSApiException(
          'Research OS ไม่ได้รับ Google OAuth state',
        );
      }
      final rawUrl = response['authorization_url']?.toString().trim();
      if (rawUrl == null || rawUrl.isEmpty) {
        throw const ResearchOSApiException(
          'Research OS ไม่ได้รับ Google authorization URL',
        );
      }
      final uri = Uri.tryParse(rawUrl);
      if (uri == null ||
          uri.scheme != 'https' ||
          uri.host != 'accounts.google.com') {
        throw const ResearchOSApiException(
          'Google authorization URL ต้องเป็น HTTPS จาก accounts.google.com',
        );
      }
      final opened = await launchUrl(
        uri,
        mode: LaunchMode.externalApplication,
      );
      if (!opened) {
        throw const ResearchOSApiException('เปิดหน้า Google Sign-In ไม่สำเร็จ');
      }
      if (!mounted) return;
      setState(() {
        _message =
            'กำลังรอการยืนยันจาก Google… กรุณาทำรายการในเบราว์เซอร์ให้เสร็จ';
      });

      final handoff = await _waitForGoogleHandoff(state);
      if (!mounted) return;
      final session = handoff['session']?.toString().trim() ?? '';
      if (handoff['connected'] != true || session.isEmpty) {
        throw const ResearchOSApiException(
          'Google Sign-In ไม่ได้ส่ง Research OS session กลับมา',
        );
      }
      widget.apiClient.setSession(session);
      final account = handoff['account'] is Map
          ? handoff['account'] as Map
          : const <String, Object?>{};
      final email = account['email']?.toString().trim() ?? '';
      setState(() {
        _message = email.isEmpty
            ? 'Google Sign-In สำเร็จ'
            : 'Google Sign-In สำเร็จ: $email';
      });
    } on Object catch (error) {
      if (!mounted) return;
      setState(() {
        _error = true;
        _message = error.toString();
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<Map<String, dynamic>> _waitForGoogleHandoff(String state) async {
    for (var attempt = 0; attempt < 120; attempt++) {
      if (!mounted) {
        throw const ResearchOSApiException(
          'Google Sign-In was interrupted before completion.',
        );
      }
      try {
        return await widget.apiClient.exchangeGoogleIdentityHandoff(state);
      } on ResearchOSApiException catch (error) {
        final statusCode = error.statusCode;
        final retryable = statusCode == 401 ||
            statusCode == 408 ||
            statusCode == 429 ||
            (statusCode != null && statusCode >= 500);
        if (!retryable) rethrow;
        await Future<void>.delayed(const Duration(seconds: 1));
      }
    }
    throw const ResearchOSApiException(
      'Google Sign-In timed out. Start again and complete Google consent promptly.',
    );
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 520),
          child: Padding(
            padding: const EdgeInsets.all(28),
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(32),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    Container(
                      width: 72,
                      height: 72,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        color: scheme.primaryContainer,
                        borderRadius: BorderRadius.circular(22),
                      ),
                      child: Icon(
                        Icons.account_circle_outlined,
                        size: 42,
                        color: scheme.onPrimaryContainer,
                      ),
                    ),
                    const SizedBox(height: 22),
                    Text(
                      'Research OS',
                      style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                            fontWeight: FontWeight.w800,
                          ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Your intelligent research workspace',
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.bodyLarge,
                    ),
                    const SizedBox(height: 28),
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton.icon(
                        onPressed: _busy ? null : _continueWithGoogle,
                        icon: _busy
                            ? const SizedBox(
                                width: 18,
                                height: 18,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.login),
                        label: Text(
                          _busy ? 'กำลังเปิด Google…' : 'Continue with Google',
                        ),
                      ),
                    ),
                    const SizedBox(height: 18),
                    Text(
                      'ใช้สำหรับ Research OS identity/session เท่านั้น\nไม่ขอสิทธิ์ Google Calendar, Drive หรือ Gmail',
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    if (_message != null) ...<Widget>[
                      const SizedBox(height: 18),
                      Text(
                        _message!,
                        textAlign: TextAlign.center,
                        style: TextStyle(color: _error ? scheme.error : scheme.primary),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
