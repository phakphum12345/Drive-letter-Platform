import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:research_os_flutter/src/api/research_os_api_client.dart';
import 'package:research_os_flutter/src/features/auth/google_login_page.dart';

class FakeGoogleIdentityApiClient extends ResearchOSApiClient {
  FakeGoogleIdentityApiClient({this.authorizationUrl})
      : super(baseUrl: 'https://research-os.test');

  final String? authorizationUrl;
  int handoffPolls = 0;
  String? receivedSession;

  @override
  Future<Map<String, dynamic>> startGoogleIdentitySignIn() async =>
      <String, dynamic>{
        'state': 'google-state-123',
        'authorization_url': authorizationUrl ??
            'https://accounts.google.com/o/oauth2/v2/auth?client_id=test',
      };

  @override
  Future<Map<String, dynamic>> exchangeGoogleIdentityHandoff(
    String state,
  ) async {
    expect(state, 'google-state-123');
    handoffPolls++;
    if (handoffPolls < 3) {
      throw const ResearchOSApiException(
        'Google handoff is not ready yet.',
        statusCode: 401,
      );
    }
    return <String, dynamic>{
      'connected': true,
      'session': 'google-session-token',
      'account': <String, dynamic>{
        'email': 'owner@example.com',
      },
    };
  }

  @override
  void setSession(String token) {
    receivedSession = token;
    super.setSession(token);
  }

  @override
  void close() {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const launcherChannel = MethodChannel('plugins.flutter.io/url_launcher');

  setUp(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
      launcherChannel,
      (call) async => true,
    );
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(launcherChannel, null);
  });

  testWidgets('Google sign-in exchanges the one-time handoff for a session',
      (tester) async {
    final client = FakeGoogleIdentityApiClient();
    addTearDown(client.close);

    await tester.pumpWidget(
      MaterialApp(home: GoogleLoginPage(apiClient: client)),
    );
    await tester.tap(find.text('Continue with Google'));
    await tester.pump();

    for (var frame = 0; frame < 5 && client.receivedSession == null; frame++) {
      await tester.pump(const Duration(seconds: 1));
      await tester.pump();
    }

    expect(client.handoffPolls, 3);
    expect(client.receivedSession, 'google-session-token');
    expect(find.text('Google Sign-In สำเร็จ: owner@example.com'), findsOneWidget);
  });

  testWidgets('Google sign-in rejects a non-Google authorization URL',
      (tester) async {
    final client = FakeGoogleIdentityApiClient(
      authorizationUrl: 'https://attacker.example/authorize',
    );
    addTearDown(client.close);

    await tester.pumpWidget(
      MaterialApp(home: GoogleLoginPage(apiClient: client)),
    );
    await tester.tap(find.text('Continue with Google'));
    await tester.pump();

    expect(client.handoffPolls, 0);
    expect(client.receivedSession, isNull);
    expect(
      find.textContaining('accounts.google.com'),
      findsOneWidget,
    );
  });
}
