# Repository Bootstrap Defaults

## Source provenance

- Source repository: https://github.com/phakphum12345/Drive-letter
- Source snapshot: 226b929cc4a54ae92f19774285867946b1a5c896
- Destination repository: https://github.com/phakphum12345/Drive-letter-Platform
- Source Git history is intentionally not copied into the destination.

## Initial safety posture

- Source workflows are quarantined in .github/workflows-disabled-source.
- Do not activate workflows until each workflow has been reviewed.
- Never copy local credentials, .env files, private keys, or runner state.
- Run security checks, tests, and a diff review before the initial commit.
- Configure repository secrets and branch protection separately in GitHub.

## Status

Bootstrap files are initial defaults, not proof of production readiness.
CI, deployment, runner access, and branch protections remain to be verified.
