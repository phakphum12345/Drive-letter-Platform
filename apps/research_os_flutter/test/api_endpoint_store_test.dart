import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:research_os_flutter/src/api/api_endpoint_store.dart';

void main() {
  test('build default follows the compile-time API contract', () {
    const expected = String.fromEnvironment(
      'RESEARCH_OS_API_BASE_URL',
      defaultValue: ApiEndpointStore.renderDefault,
    );
    expect(ApiEndpointStore.buildDefault, expected);
  });

  test('local endpoint remains a valid explicit profile value', () {
    expect(
      ApiEndpointStore.normalize(ApiEndpointStore.localDefault),
      ApiEndpointStore.localDefault,
    );
  });
  test('saved Local endpoint is not silently migrated to the build default', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'research_os_api_base_url_v1': ApiEndpointStore.localDefault,
    });

    expect(await ApiEndpointStore.load(), ApiEndpointStore.localDefault);
  });

  test('saved Render endpoint remains explicit across builds', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'research_os_api_base_url_v1': ApiEndpointStore.renderDefault,
    });

    expect(await ApiEndpointStore.load(), ApiEndpointStore.renderDefault);
  });

}
