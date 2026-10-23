# Research OS Authentication Convergence Plan

## Agreed implementation order

Work one slice at a time. Do not start the next slice until the current slice has source-backed evidence, regression coverage, and its applicable CI checks have been reviewed.

1. **Shared UI and logout**
   - Audit the canonical Flutter UI, navigation, login/authenticated states, and logout behavior.
   - Keep Windows, Web, and iOS on the shared product UI; host runners must not create a competing auth/navigation surface.
   - Logout must call the Research OS API, clear the client-held session only after successful server confirmation, and return to the QR login surface.
   - Do not disconnect Google Workspace as a side effect of Research OS sign-out.
2. **QR pairing**
   - Verify start/status/cancel/handoff endpoints against the active pairing contract.
   - Cover expiry, cancellation, replay, secret mismatch, single-use handoff, invalid responses, and session establishment.
   - Confirm the QR flow works end-to-end in an isolated candidate environment.
3. **Cross-system relationship**
   - Trace UI → API → backend session authority → provider handoff across all supported app targets.
   - Establish one explicit session lifecycle and define ownership of authentication state, session revocation, and endpoint switching.
   - Document which flows share the Research OS session and which remain separate (especially Google Workspace credentials).
4. **Google Login / OAuth**
   - Only after the preceding slices are verified, determine completion status from source, tests, contracts, and runtime evidence.
   - Implement only proven gaps in OAuth state parsing, browser return/polling, one-time handoff, secure session storage, and sign-out/invalid-session handling.
   - Keep Google identity OAuth separate from Google Workspace OAuth; do not infer completion from a page or start endpoint alone.

## Engineering and release rules

- Evidence first: inspect source, callers, configuration, tests, contracts, and workflows before changing behavior.
- Fix shared root causes; do not disable gates or alter expected outcomes merely to obtain green checks.
- Keep candidate changes isolated from production and protected data. Do not deploy or merge without the agreed evidence.
- Add regression tests for behavior and security boundaries; report honestly which tests ran and which did not.
- Verify all required checks against the exact final commit SHA before declaring a slice complete.
- A UI screenshot or static source inspection is not proof of runtime end-to-end behavior.

## Current state

- This plan is recorded as the agreed work order.
- UI/logout is the first candidate slice in PR #9.
- QR, cross-system reconciliation, and Google OAuth have not been declared complete.
- Google OAuth completion remains unverified and is intentionally deferred until the fourth step.
