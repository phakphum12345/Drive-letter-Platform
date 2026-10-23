import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:research_os_flutter/src/ui/research_os_sidebar_v2.dart';

void main() {
  testWidgets('shared sidebar exposes an accessible logout action', (tester) async {
    var logoutCount = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Row(
            children: <Widget>[
              ResearchOSSidebarV2(
                expanded: true,
                selectedIndex: 0,
                onToggle: () {},
                onSelected: (_) {},
                onLogout: () => logoutCount++,
              ),
              const Expanded(child: SizedBox()),
            ],
          ),
        ),
      ),
    );

    final logout = find.byKey(const ValueKey('research-os-logout'));
    expect(logout, findsOneWidget);
    expect(find.text('ออกจากระบบ'), findsOneWidget);
    await tester.tap(logout);
    expect(logoutCount, 1);
    expect(tester.takeException(), isNull);
  });

  testWidgets('logout action is omitted when no logout callback is supplied', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ResearchOSSidebarV2(
            expanded: false,
            selectedIndex: 0,
            onToggle: () {},
            onSelected: (_) {},
          ),
        ),
      ),
    );

    expect(find.byKey(const ValueKey('research-os-logout')), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
