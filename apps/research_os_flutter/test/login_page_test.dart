import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:research_os_flutter/src/api/research_os_api_client.dart';
import 'package:research_os_flutter/src/features/auth/login_page.dart';


void main() {
  testWidgets(
    'refresh cancels the previous pairing and ignores its late status',
    (tester) async {
      tester.view.physicalSize = const Size(800, 1000);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final firstStatus = Completer<http.Response>();
      var starts = 0;
      var statusRequests = 0;
      var cancelCalls = 0;
      final handoffSecrets = <String>[];
      var authenticated = 0;
      final client = ResearchOSApiClient(
        baseUrl: 'http://research-os.test',
        client: MockClient((request) async {
          switch (request.url.path) {
            case '/v1/auth/pairing/start':
              starts++;
              final id = 'pair-$starts';
              final secret = 'secret-$starts';
              return http.Response(
                jsonEncode({
                  'pairing_id': id,
                  'pairing_secret': secret,
                  'expires_at': 9999999999,
                  'status': 'PENDING',
                  'qr_payload':
                      'https://research-os.test/v1/auth/pairing/open?pairing_id=$id&secret=$secret',
                }),
                201,
                headers: {'content-type': 'application/json'},
              );
            case '/v1/auth/pairing/status':
              statusRequests++;
              final id = request.url.queryParameters['pairing_id'];
              if (id == 'pair-1') return firstStatus.future;
              return http.Response(
                jsonEncode({
                  'pairing_id': 'pair-2',
                  'status': 'CONNECTED',
                  'connected': true,
                  'handoff_ready': true,
                }),
                200,
                headers: {'content-type': 'application/json'},
              );
            case '/v1/auth/pairing/cancel':
              cancelCalls++;
              return http.Response(
                jsonEncode({'cancelled': true}),
                200,
                headers: {'content-type': 'application/json'},
              );
            case '/v1/auth/providers/handoff':
              final secret = request.headers['x-research-os-oauth-state']!;
              handoffSecrets.add(secret);
              return http.Response(
                jsonEncode({
                  'connected': true,
                  'session': 'session-$secret',
                }),
                200,
                headers: {'content-type': 'application/json'},
              );
            case '/v1/auth/status':
              expect(request.headers['x-research-os-session'], 'session-secret-2');
              return http.Response(
                jsonEncode({'connected': true, 'account': {'user_id': 'github:123'}}),
                200,
                headers: {'content-type': 'application/json'},
              );
            default:
              fail('Unexpected request: ${request.method} ${request.url}');
          }
        }),
      );
      addTearDown(client.close);
      await tester.pumpWidget(
        MaterialApp(
          home: LoginPage(
            apiClient: client,
            connectionProfile: 'research_os',
            onConnectionChanged: (_) async {},
            onAuthenticated: () => authenticated++,
          ),
        ),
      );
      // The pairing poller intentionally remains active while the first status
      // response is pending, so pumpAndSettle would wait forever. Pump bounded
      // frames until the request is observed instead.
      for (var frame = 0; frame < 20 && statusRequests == 0; frame++) {
        await tester.pump(const Duration(milliseconds: 50));
      }
      expect(starts, 1);
      expect(statusRequests, 1);

      final refreshButton = find.byKey(const ValueKey('refresh-qr-button'));
      // The status request can begin before Flutter has rendered the enabled
      // refresh state. Wait for the actual UI state, not an arbitrary delay.
      for (var frame = 0;
          frame < 20 ||
              tester.widget<OutlinedButton>(refreshButton).onPressed == null;
          frame++) {
        if (frame >= 20) break;
        await tester.pump(const Duration(milliseconds: 50));
      }
      expect(
        tester.widget<OutlinedButton>(refreshButton).onPressed,
        isNotNull,
        reason: 'Refresh must be enabled once the first pairing has started.',
      );
      await tester.ensureVisible(refreshButton);
      await tester.pump();
      // The first pairing status request is deliberately unresolved; do not
      // use pumpAndSettle while that asynchronous poll is pending.
      await tester.tap(refreshButton);
      await tester.pump();
      for (var frame = 0; frame < 20 && authenticated == 0; frame++) {
        await tester.pump(const Duration(milliseconds: 50));
      }
      expect(starts, 2);
      expect(cancelCalls, 1);
      expect(authenticated, 1);

      firstStatus.complete(
        http.Response(
          jsonEncode({
            'pairing_id': 'pair-1',
            'status': 'CONNECTED',
            'connected': true,
            'handoff_ready': true,
          }),
          200,
          headers: {'content-type': 'application/json'},
        ),
      );
      await tester.pumpAndSettle();
      expect(handoffSecrets, <String>['secret-2']);
      expect(authenticated, 1);
    },
  );

  testWidgets('shared auth surface uses QR pairing instead of login choices', (tester) async {
    var authenticated = 0;
    final client = ResearchOSApiClient(
      baseUrl: 'http://research-os.test',
      client: MockClient((request) async {
        switch (request.url.path) {
          case '/v1/auth/pairing/start':
            return http.Response(
              jsonEncode({
                'pairing_id': 'pair-123',
                'pairing_secret': 'secret-123',
                'expires_at': 9999999999,
                'status': 'PENDING',
                'qr_payload': 'https://research-os.test/v1/auth/pairing/open?pairing_id=pair-123&secret=secret-123',
              }),
              201,
              headers: {'content-type': 'application/json'},
            );
          case '/v1/auth/pairing/status':
            return http.Response(
              jsonEncode({
                'pairing_id': 'pair-123',
                'status': 'CONNECTED',
                'expires_at': 9999999999,
                'connected': true,
                'handoff_ready': true,
                'account': {'user_id': 'github:123', 'email': 'owner@example.com', 'role': 'owner'},
              }),
              200,
              headers: {'content-type': 'application/json'},
            );
          case '/v1/auth/providers/handoff':
            expect(request.headers['x-research-os-oauth-state'], 'secret-123');
            return http.Response(
              jsonEncode({'connected': true, 'session': 'session-token'}),
              200,
              headers: {'content-type': 'application/json'},
            );
          case '/v1/auth/status':
            expect(request.headers['x-research-os-session'], 'session-token');
            return http.Response(
              jsonEncode({'connected': true, 'account': {'user_id': 'github:123'}}),
              200,
              headers: {'content-type': 'application/json'},
            );
          default:
            fail('Unexpected request: ${request.method} ${request.url}');
        }
      }),
    );
    addTearDown(client.close);
    await tester.pumpWidget(
      MaterialApp(
        home: LoginPage(
          apiClient: client,
          connectionProfile: 'research_os',
          onConnectionChanged: (_) async {},
          onAuthenticated: () => authenticated++,
        ),
      ),
    );
    // Pump a bounded number of frames instead of waiting for all animations
    // to settle; the page intentionally includes a QR status poller.
    for (var frame = 0; frame < 20 && authenticated == 0; frame++) {
      await tester.pump(const Duration(milliseconds: 50));
    }
    // onAuthenticated is called immediately after setState; pump once so the
    // rebuilt connected-state widget tree is observable to finders.
    await tester.pump();
    expect(authenticated, 1);
    expect(find.byType(CircularProgressIndicator), findsNothing);
    expect(find.text('Research OS'), findsOneWidget);
    expect(find.text('Scan to Connect'), findsOneWidget);
    expect(find.text('PORT'), findsOneWidget);
    expect(find.text('PORT 1'), findsOneWidget);
    expect(find.byKey(const ValueKey('refresh-qr-button')), findsOneWidget);
    expect(find.text('LOGIN'), findsNothing);
    expect(find.text('Select Login Method'), findsNothing);
    expect(find.text('USER LEVEL'), findsNothing);
    expect(find.text('Windows'), findsNothing);
    expect(find.text('GitHub'), findsNothing);
    expect(find.text('Google'), findsNothing);
    expect(find.text('None'), findsNothing);
    expect(find.text('Custom'), findsNothing);
    expect(authenticated, 1);
  });
  testWidgets('QR handoff does not enter the app when the API rejects its session', (tester) async {
    var authenticated = 0;
    final observedSessionHeaders = <String?>[];
    final client = ResearchOSApiClient(
      baseUrl: 'http://research-os.test',
      client: MockClient((request) async {
        switch (request.url.path) {
          case '/v1/auth/pairing/start':
            return http.Response(
              jsonEncode({
                'pairing_id': 'pair-invalid',
                'pairing_secret': 'secret-invalid',
                'expires_at': 9999999999,
                'status': 'PENDING',
                'qr_payload': 'https://research-os.test/v1/auth/pairing/open?pairing_id=pair-invalid&secret=secret-invalid',
              }),
              201,
              headers: {'content-type': 'application/json'},
            );
          case '/v1/auth/pairing/status':
            return http.Response(
              jsonEncode({
                'pairing_id': 'pair-invalid',
                'status': 'CONNECTED',
                'connected': true,
                'handoff_ready': true,
              }),
              200,
              headers: {'content-type': 'application/json'},
            );
          case '/v1/auth/providers/handoff':
            return http.Response(
              jsonEncode({'connected': true, 'session': 'invalid-session'}),
              200,
              headers: {'content-type': 'application/json'},
            );
          case '/v1/auth/status':
            observedSessionHeaders.add(request.headers['x-research-os-session']);
            return http.Response(
              jsonEncode({'connected': false, 'account': null}),
              200,
              headers: {'content-type': 'application/json'},
            );
          case '/v1/auth/pairing/cancel':
            return http.Response(
              jsonEncode({'cancelled': true}),
              200,
              headers: {'content-type': 'application/json'},
            );
          default:
            fail('Unexpected request: ${request.method} ${request.url}');
        }
      }),
    );
    addTearDown(client.close);

    await tester.pumpWidget(
      MaterialApp(
        home: LoginPage(
          apiClient: client,
          connectionProfile: 'research_os',
          onConnectionChanged: (_) async {},
          onAuthenticated: () => authenticated++,
        ),
      ),
    );
    for (var frame = 0; frame < 20 && observedSessionHeaders.isEmpty; frame++) {
      await tester.pump(const Duration(milliseconds: 50));
    }
    await tester.pump();

    expect(observedSessionHeaders, <String?>['invalid-session']);
    expect(authenticated, 0);
    expect(find.textContaining('session could not be verified'), findsOneWidget);

    // A rejected session must be cleared, not retained for later API calls.
    await client.getAuthStatus();
    expect(observedSessionHeaders, <String?>['invalid-session', null]);
  });

}
