# Research OS Authentication, QR, Device and UI Audit

**Audit date:** 2026-10-19
**Working branch:** `fix/qr-device-ui-flow-audit`
**Status:** In progress; do not treat this report as release approval.

## End-to-end route map

| Stage | Source of truth | Current behavior | Verification boundary |
|---|---|---|---|
| QR start | `tools/research_os_api/server.py` `POST /v1/auth/pairing/start` | Creates a short-lived pairing and returns a QR URL | API tests; public URL must be HTTPS, loopback HTTP is allowed for local development |
| QR open/status/cancel/approve | `tools/research_os_api/qr_pairing.py`, `server.py` | Scanner must authenticate on the phone/browser, then explicitly approve sharing that existing session; a one-time handoff delivers that same session to the QR device | Automated route tests cover approval required, single-use handoff, and approval replay/race protection |
| Provider selection | `GET /v1/auth/pairing/open` | Lists only providers marked available by server configuration | Configuration and route tests; not live OAuth proof |
| OAuth callback | `server_auth_routes.py`, `multi_login_runtime.py`, `google_identity.py` | OAuth callback authenticates the scanning device and returns it to the approval page; pairing does not complete until the existing session explicitly approves | Automated tests mock provider HTTP; live provider consent/callback still requires runtime evidence |
| Session/handoff | `auth_session.py`, `oauth_handoff.py` | Signed Research OS session; one-time, short-lived handoff; sign-out revokes session | Automated unit/route coverage; real multi-device runtime still unverified |
| Google Workspace | `google_oauth.py`, `google_workspace.py`, `/v1/google-workspace/oauth/*` | Separate Workspace token and consent path from Google Identity sign-in | Must remain separate; workspace disconnect must not be interpreted as Research OS sign-out |
| Login/logout UI | `research_os_app.dart`, `login_page.dart`, `app_shell.dart` | App checks session status on startup; logout waits for API sign-out before clearing local session | Widget and API tests; live API and actual device run remain unverified |

## Root causes addressed in this change set

1. QR refresh could leave the prior polling loop alive. A delayed response from the previous pairing could still be processed after a new QR was created.
2. A pairing-start response arriving after refresh/disposal could leave an orphaned pending pairing.
3. Pairing-status/handoff HTTP errors were all swallowed as retryable errors, so terminal 4xx failures could remain hidden until the polling loop timed out.
4. A public Host fallback could generate an HTTP QR URL. Public deployments now require an explicitly configured HTTPS base URL; HTTP is allowed only for loopback local development.

### Developer API code-apply 403

The source audit found an allowlist configuration defect in `flutter_code_tool.apply()`: `RESEARCH_OS_CODE_OWNER_IDS or RESEARCH_OS_OWNER_EMAILS` treated the two supported Owner identity lists as mutually exclusive, so a configured ID list could shadow the email list. The implementation now combines both allowlists and compares normalized identities, with a regression test for an email-listed Owner when the ID list is also set. The observed 403 is still not proof that this was the only live cause: runtime principal and environment values were not present in the supplied log. The 403 emitted by the non-owner authorization regression test is expected security behavior and must remain.

## Device lifecycle gap — not yet complete

The QR route now requires an authenticated browser session and explicit approval before handing that same session to the QR device. The source audit did **not** find a complete device registry with stable device IDs, per-device status/history, or per-device revocation. The repository's `device_id` references in platform evidence schemas are not proof of an authentication device registry. Do not claim device lifecycle is complete until a device contract, authorized register/list/revoke routes, session binding rules, and tests exist.

## Flutter UI inventory

The shared navigation registry currently has 18 destinations. Page files under `apps/research_os_flutter/lib/src/features` include:

- Agent Center — `agents/agent_center_page.dart`
- API Live Demo — `api_live/api_live_demo_page.dart`
- QR Login — `auth/login_page.dart`
- Google Identity — `auth/google_login_page.dart`
- Brain Skills — `brain_skills/brain_skills_page.dart`
- AI Chat — `chat/chat_page.dart`
- Friend Workspace — `chat/friend_workspace_page.dart`
- Voice Conversation — `chat/voice_conversation_page.dart`
- Check-in — `checkin/check_in_page.dart`
- Control Center — `control_center/native_control_center_page.dart`
- Developer Access — `developer_access/developer_access_page.dart`
- Flutter Code Tool — `developer_access/flutter_code_tool_page.dart`
- Friend Connect — `friend/friend_connect_page.dart`
- GitHub Dashboard — `github/github_dashboard_page.dart`
- Google Workspace — `google_workspace/google_workspace_page.dart`
- Knowledge Graph — `graph/knowledge_graph_page.dart`
- Home — `home/home_page.dart`
- Library — `library/library_page.dart`
- Local API & Service — `local_api/local_api_control_page.dart`
- System Monitor — `monitor/system_monitor_page.dart`
- Owner — `owner/owner_experience_page.dart`
- Projects — `projects/project_experience_page.dart`
- Settings — `settings/settings_page.dart`
- Workflows — `workflows/workflow_experience_page.dart`

The desktop shell test already traverses all 18 registered navigation destinations and checks for Flutter exceptions. This change adds the same traversal at a narrow 390×844 viewport, plus a QR-refresh race regression test. These are widget/layout smoke tests, **not** a substitute for visually reviewing captured app screenshots.

## Evidence still required before calling this complete

- [ ] Exact-SHA CI completes without failures.
- [ ] Live Google Identity, GitHub and Microsoft OAuth callbacks tested with configured provider apps.
- [ ] Google Workspace connect/disconnect verified independently from identity login/logout.
- [ ] Device registration and per-device revocation designed, implemented and tested.
- [ ] Login, each of the 18 navigation pages, Google Identity, Workspace, and logout screens visually inspected at desktop and narrow/mobile sizes using actual rendered screenshots.
- [ ] Login/logout confirmed against the intended deployed/local API and at least two real devices.
- [ ] No merge or deployment until explicitly approved.
