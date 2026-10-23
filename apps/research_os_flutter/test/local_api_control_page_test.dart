import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:research_os_flutter/src/features/local_api/local_api_control_page.dart';
import 'package:research_os_flutter/src/platform/local_api_manager.dart';

class _FakeLocalApiManager extends LocalApiManager {
  _FakeLocalApiManager();

  int installCalls = 0;
  int uninstallCalls = 0;

  @override
  bool get supported => true;

  @override
  Future<LocalApiCommandResult> serviceStatus() async =>
      const LocalApiCommandResult(ok: true, message: 'status');

  @override
  Future<LocalApiCommandResult> installService() async {
    installCalls++;
    return const LocalApiCommandResult(ok: true, message: 'installed');
  }

  @override
  Future<LocalApiCommandResult> uninstallService() async {
    uninstallCalls++;
    return const LocalApiCommandResult(ok: true, message: 'uninstalled');
  }
}

void main() {
  testWidgets('install requires acknowledgement and cancel has no side effect',
      (tester) async {
    final manager = _FakeLocalApiManager();
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: LocalApiControlPage(manager: manager))),
    );
    await tester.pumpAndSettle();

    final action = find.text('ติดตั้ง Service').first;
    await tester.ensureVisible(action);
    await tester.pumpAndSettle();
    await tester.tap(action);
    await tester.pumpAndSettle();

    expect(
      find.textContaining('ติดตั้งเฉพาะ Windows Service ResearchOSService'),
      findsOneWidget,
    );
    final confirmButton = find.descendant(
      of: find.byType(AlertDialog),
      matching: find.byType(FilledButton),
    );
    expect(tester.widget<FilledButton>(confirmButton).onPressed, isNull);

    await tester.tap(find.text('ยกเลิก'));
    await tester.pumpAndSettle();
    expect(manager.installCalls, 0);
  });

  testWidgets('install runs only after acknowledgement is checked',
      (tester) async {
    final manager = _FakeLocalApiManager();
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: LocalApiControlPage(manager: manager))),
    );
    await tester.pumpAndSettle();

    final action = find.text('ติดตั้ง Service').first;
    await tester.ensureVisible(action);
    await tester.pumpAndSettle();
    await tester.tap(action);
    await tester.pumpAndSettle();

    await tester.tap(find.byType(CheckboxListTile));
    await tester.pumpAndSettle();
    final confirmButton = find.descendant(
      of: find.byType(AlertDialog),
      matching: find.byType(FilledButton),
    );
    expect(tester.widget<FilledButton>(confirmButton).onPressed, isNotNull);

    await tester.tap(confirmButton);
    await tester.pumpAndSettle();
    expect(manager.installCalls, 1);
  });

  testWidgets('uninstall shows service-only warning and cancel has no side effect',
      (tester) async {
    final manager = _FakeLocalApiManager();
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: LocalApiControlPage(manager: manager))),
    );
    await tester.pumpAndSettle();

    final action = find.text('ถอน Service').first;
    await tester.ensureVisible(action);
    await tester.pumpAndSettle();
    await tester.tap(action);
    await tester.pumpAndSettle();

    expect(
      find.textContaining('ถอนการลงทะเบียน Windows Service เท่านั้น'),
      findsOneWidget,
    );
    await tester.tap(find.text('ยกเลิก'));
    await tester.pumpAndSettle();
    expect(manager.uninstallCalls, 0);
  });

  testWidgets('uninstall runs only after acknowledgement is checked',
      (tester) async {
    final manager = _FakeLocalApiManager();
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: LocalApiControlPage(manager: manager))),
    );
    await tester.pumpAndSettle();

    final action = find.text('ถอน Service').first;
    await tester.ensureVisible(action);
    await tester.pumpAndSettle();
    await tester.tap(action);
    await tester.pumpAndSettle();

    final confirmButton = find.descendant(
      of: find.byType(AlertDialog),
      matching: find.byType(FilledButton),
    );
    expect(tester.widget<FilledButton>(confirmButton).onPressed, isNull);

    await tester.tap(find.byType(CheckboxListTile));
    await tester.pumpAndSettle();
    expect(tester.widget<FilledButton>(confirmButton).onPressed, isNotNull);

    await tester.tap(confirmButton);
    await tester.pumpAndSettle();
    expect(manager.uninstallCalls, 1);
  });
}
